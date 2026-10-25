"""Тесты метрик списка учеников: долг, баланс, уроки, модалки отчёта и уроков.

change student-list-reference: сводка задолженности, агрегаты карточек
(баланс, «Проведено», следующий урок, первая оплата), сортировка и
переключатель «Удалённые», модалки «Уроки» и «Отчёт».
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.database import SessionLocal
from app.lesson.models.lesson import Lesson

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="metrics-owner@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "metrics-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _completed_lesson(student_id: str, *, starts_at, price=1200):
    with SessionLocal() as db:
        db.add(
            Lesson(
                student_id=student_id,
                type="individual",
                starts_at=starts_at,
                duration_min=60,
                price=price,
                status="completed",
            )
        )
        db.commit()


# --------------------------------------------------------------------------
# Метрики карточек и таблицы
# --------------------------------------------------------------------------


def test_card_counts_group_lessons(client, owner, student_factory, group_factory,
                                   group_member_factory):
    """«Проведено» считает и групповые уроки, где ученик участник."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    group_id = group_factory(tutor_id=owner)
    group_member_factory(group_id=group_id, student_id=student_id)
    _completed_lesson(student_id, starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
    with SessionLocal() as db:
        db.add(
            Lesson(
                group_id=group_id,
                type="group",
                starts_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
                duration_min=60,
                status="completed",
            )
        )
        db.commit()

    card = client.get("/tutor/students").text
    start = card.index('class="student-stats"')
    assert "Проведено: 2" in card[start : card.index("student-actions", start)]


def test_balance_rendered_in_rubles_with_colors(client, owner, student_factory,
                                                operation_factory):
    """Баланс — знаком рубля: долг красным (класс), плюс зелёным; «$» нет."""
    debtor = student_factory(tutor_id=owner, first_name="Должник")
    creditor = student_factory(tutor_id=owner, first_name="Кредитор")
    operation_factory(student_id=debtor, kind="lesson", amount=1200, status=None)
    operation_factory(student_id=creditor, amount=800)

    table = client.get("/tutor/students").text
    assert "\u22121\u00a0200\u00a0₽" in table
    assert "800\u00a0₽" in table
    assert "money-value--debt" in table
    assert "money-value--positive" in table
    assert "$" not in table


def test_next_lesson_label_today_and_future(client, owner, student_factory):
    """Ближайший запланированный урок: «Сегодня/Завтра в HH:MM», дальше — дата."""
    soon = student_factory(tutor_id=owner, first_name="Скоро")
    later = student_factory(tutor_id=owner, first_name="Позже")
    with SessionLocal() as db:
        db.add(
            Lesson(
                student_id=soon,
                type="individual",
                # Час вперёд: сегодня, а около полуночи — «Завтра», оба верны.
                starts_at=datetime.now(UTC) + timedelta(hours=1),
                duration_min=60,
                status="planned",
            )
        )
        db.add(
            Lesson(
                student_id=later,
                type="individual",
                starts_at=datetime(2027, 1, 10, 10, 0, tzinfo=UTC),
                duration_min=60,
                status="planned",
            )
        )
        db.commit()

    page = client.get("/tutor/students").text
    assert "Нет запланированных уроков" not in page
    # Урок в будущем показывается датой «D мес. в HH:MM» в зоне педагога (UTC).
    assert "10 янв. в 10:00" in page
    assert ("Сегодня в" in page) or ("Завтра в" in page)


def test_remaining_lessons_from_positive_balance(client, owner, student_factory,
                                                 operation_factory):
    """«Осталось: N занятий» — баланс // цена последнего урока с ценой.

    Баланс 2500 и цена 1200 дают 2 занятия; при отрицательном балансе или
    неизвестной цене строки нет вовсе (честно, а не «0»).
    """
    rich = student_factory(tutor_id=owner, first_name="СОстатком")
    poor = student_factory(tutor_id=owner, first_name="ВДолге")
    noprice = student_factory(tutor_id=owner, first_name="БезЦены")
    operation_factory(student_id=rich, amount=2500)
    _completed_lesson(rich, starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
    operation_factory(student_id=poor, kind="lesson", amount=1200, status=None)
    _completed_lesson(poor, starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC))
    operation_factory(student_id=noprice, amount=900)

    page = client.get("/tutor/students").text
    assert "Осталось: 2 занятия" in page
    # У должника и ученика без цены строки «Осталось» нет.
    assert page.count("Осталось:") == 1


def test_table_shows_appeared_and_first_payment(client, owner, student_factory,
                                                operation_factory):
    """Колонки «Появился» и «Первая оплата»: даты или прочерк."""
    with_payment = student_factory(tutor_id=owner, first_name="СПлатежом")
    without = student_factory(tutor_id=owner, first_name="БезПлатежа")
    operation_factory(student_id=with_payment, amount=2000)

    table = client.get("/tutor/students").text
    row = table[table.index(f'id="student-row-{with_payment}"') :]
    row = row[: row.index("</tr>")]
    # occurred_at платежа из фабрики — 22.10.2026, зона педагога UTC.
    assert "22.10.2026" in row
    row2 = table[table.index(f'id="student-row-{without}"') :]
    row2 = row2[: row2.index("</tr>")]
    assert "—" in row2


# --------------------------------------------------------------------------
# Панель долга и фильтр должников
# --------------------------------------------------------------------------


def test_debt_panel_sums_negative_balances(client, owner, student_factory,
                                           operation_factory):
    """Панель: сумма долгов и число должников по видимому списку."""
    operation_factory(student_id=student_factory(tutor_id=owner, first_name="А"),
                      kind="lesson", amount=1200, status=None)
    operation_factory(student_id=student_factory(tutor_id=owner, first_name="Б"),
                      kind="lesson", amount=900, status=None)
    operation_factory(student_id=student_factory(tutor_id=owner, first_name="В"),
                      amount=500)

    page = client.get("/tutor/students").text
    assert "Общая задолженность" in page
    assert "2\u00a0100\u00a0₽" in page
    assert "Должников <span>2</span>" in page


def test_debt_panel_hidden_without_debt(client, owner, student_factory,
                                        operation_factory):
    """Нет должников — панели нет совсем."""
    operation_factory(student_id=student_factory(tutor_id=owner, first_name="В"),
                      amount=500)
    assert "Общая задолженность" not in client.get("/tutor/students").text


def test_debtors_filter_keeps_only_debtors(client, owner, student_factory,
                                           operation_factory):
    """«Показать только их»: остаются должники, ссылка меняется на обратную."""
    debtor = student_factory(tutor_id=owner, first_name="Должник")
    operation_factory(student_id=debtor, kind="lesson", amount=1200, status=None)
    payer = student_factory(tutor_id=owner, first_name="Плательщик")
    operation_factory(student_id=payer, amount=500)

    page = client.get("/tutor/students/list", params={"debtors": "1"}).text
    assert "Должник" in page
    assert "Плательщик" not in page
    assert "Показать всех" in page


# --------------------------------------------------------------------------
# Сортировка и «Удалённые»
# --------------------------------------------------------------------------


def test_sort_by_lastname_then_firstname(client, owner, student_factory):
    """Умолчание — по фамилии (без фамилии — по имени); «по имени» меняет порядок."""
    student_factory(tutor_id=owner, first_name="Яна")
    student_factory(tutor_id=owner, first_name="Борис", last_name="Алиев")

    by_lastname = client.get("/tutor/students/list").text
    assert by_lastname.index("Алиев") < by_lastname.index("Яна")

    by_firstname = client.get("/tutor/students/list", params={"sort": "firstname"}).text
    assert by_firstname.index("Борис") < by_firstname.index("Яна")


def test_deleted_button_drives_status_filter(client, owner, student_factory):
    """Кнопка «Удалённые» — состояние от серверного фильтра статуса."""
    student_factory(tutor_id=owner, first_name="Активная", status="active")
    student_factory(tutor_id=owner, first_name="Архивная", status="archived")

    page = client.get("/tutor/students/list", params={"status": "archived"}).text
    assert "Архивная" in page
    assert "Активная" not in page


# --------------------------------------------------------------------------
# Модалка «Уроки»
# --------------------------------------------------------------------------


def test_lessons_modal_lists_and_filters(client, owner, student_factory):
    """Модалка: уроки от новых к старым, чипы фильтра, клик откроет модалку урока."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    _completed_lesson(student_id, starts_at=datetime(2026, 10, 21, 15, 0, tzinfo=UTC))
    _completed_lesson(student_id, starts_at=datetime(2026, 10, 22, 16, 0, tzinfo=UTC))
    with SessionLocal() as db:
        db.add(
            Lesson(
                student_id=student_id,
                type="individual",
                starts_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
                duration_min=60,
                status="planned",
            )
        )
        db.commit()

    page = client.get(f"/tutor/students/{student_id}/lessons").text
    assert "Уроки: Маша" in page
    # Фиксированная высота окна: смена чипа не должна «прыгать» размером.
    assert "modal-content--list" in page
    assert page.index("22.10.2026") < page.index("21.10.2026")  # новые сверху
    assert 'hx-get="/tutor/lessons/' in page
    assert 'hx-target="#modal-lesson"' in page
    assert "Проведён" in page and "Запланирован" in page

    past = client.get(
        f"/tutor/students/{student_id}/lessons", params={"status": "completed"}
    ).text
    assert "21.10.2026" in past and "01.11.2026" not in past


def test_lessons_chips_return_content_not_modal(client, owner, student_factory):
    """Чипы перезапрашивают маршрут с `HX-Target` содержимого — и получают
    только содержимое: иначе модалка вложилась бы сама в себя (тёмный фон,
    сломанный крестик)."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    _completed_lesson(student_id, starts_at=datetime(2026, 10, 21, 15, 0, tzinfo=UTC))

    content = client.get(
        f"/tutor/students/{student_id}/lessons",
        params={"status": "completed"},
        headers={"HX-Target": "student-lessons-content"},
    ).text
    assert 'id="student-lessons-content"' in content
    assert "21.10.2026" in content
    for shell in ("modal-root", "modal-overlay", "modal-content", "Уроки: Маша"):
        assert shell not in content, f"Чипы получили оболочку окна: {shell!r}"
    # Имя radio совпадает с параметром вьюхи: htmx шлёт значение под именем
    # поля, чужое имя молча роняло фильтр (запрос уходил без `status`).
    assert 'name="status"' in content
    assert 'student-lessons-status' not in content


def test_lessons_modal_empty_state(client, owner, student_factory):
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    page = client.get(f"/tutor/students/{student_id}/lessons").text
    assert "У ученика пока нет уроков." in page


def test_lessons_modal_isolation(client, owner, tutor_factory, student_factory):
    """Чужой ученик — 404, как несуществующий."""
    other_id = tutor_factory(email="metrics-other@example.com")
    foreign = student_factory(tutor_id=other_id, first_name="Чужой")
    assert client.get(f"/tutor/students/{foreign}/lessons").status_code == 404


# --------------------------------------------------------------------------
# Модалка «Отчёт»
# --------------------------------------------------------------------------


def test_report_modal_month_totals(client, owner, student_factory,
                                   operation_factory):
    """Карточки отчёта: списано/оплачено за месяц, баланс, заработок."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    operation_factory(student_id=student_id, amount=2000)  # платёж 20.10
    _completed_lesson(student_id, starts_at=datetime(2026, 10, 21, 10, 0, tzinfo=UTC))
    client.post(f"/tutor/students/{student_id}/balance/recalculate")

    page = client.get(
        f"/tutor/students/{student_id}/report", params={"month": "2026-10"}
    ).text
    assert "Отчёт: Маша" in page
    assert "Итоги занятий и расчёт за месяц" in page
    assert "Проведено" in page and ">1</p>" in page
    assert "1\u00a0200\u00a0₽" in page and "списаний: 1" in page
    assert "2\u00a0000\u00a0₽" in page and "платежей: 1" in page
    assert "800\u00a0₽" in page  # баланс сейчас
    # Остаток: 800 // 1200 = 0 занятий — считается и показывается честно.
    assert "Осталось 0 занятий" in page
    # Заработок = списание по индивидуальному уроку.
    assert "по индивидуальным занятиям" in page
    assert "1\u00a0200\u00a0₽" in page


def test_report_modal_month_navigation(client, owner, student_factory):
    """Навигация: подпись месяца и ссылки на соседние, мусор — текущий."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    page = client.get(
        f"/tutor/students/{student_id}/report", params={"month": "2026-10"}
    ).text
    assert "Октябрь 2026 г." in page
    assert "month=2026-09" in page and "month=2026-11" in page
    assert 'hx-target="#report-content"' in page

    garbage = client.get(
        f"/tutor/students/{student_id}/report", params={"month": "мусор"}
    ).text
    assert "г.</span>" in garbage  # подпись отрисовалась без 500


def test_report_month_arrows_return_content_not_modal(client, owner, student_factory):
    """Стрелки месяцев шлют `HX-Target` содержимого и получают только его —
    модалка не вкладывается сама в себя при листании."""
    student_id = student_factory(tutor_id=owner, first_name="Маша")
    content = client.get(
        f"/tutor/students/{student_id}/report",
        params={"month": "2026-09"},
        headers={"HX-Target": "report-content"},
    ).text
    assert 'id="report-content"' in content
    assert "Сентябрь 2026 г." in content
    for shell in ("modal-root", "modal-overlay", "Отчёт: Маша"):
        assert shell not in content, f"Стрелки получили оболочку окна: {shell!r}"


def test_report_modal_isolation(client, owner, tutor_factory, student_factory):
    other_id = tutor_factory(email="metrics-other2@example.com")
    foreign = student_factory(tutor_id=other_id, first_name="Чужой")
    assert client.get(f"/tutor/students/{foreign}/report").status_code == 404
