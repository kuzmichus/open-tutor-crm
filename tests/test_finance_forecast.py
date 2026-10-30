"""Тесты вкладки «Прогноз на месяц» страницы финансов.

Поведение проверяется тем же путём, что у пользователя: те же маршруты и
query-параметры, разметка ищется по тексту и классам. Месяц прогноза в
тестах — следующий: он целиком в будущем, поэтому «запланированные уроки
до конца месяца» и «осталось недель» не зависят от того, какое сегодня
число. Текущий месяц используется там, где важна именно состоявшаяся
часть (факт).

Сценарии: карточки-метрики и их числа, цена группового урока как сумма
цен участников, ученики вне расписания, предупреждение об уроке без цены,
фиксация снимка и сравнение с фактом, выгрузка CSV, изоляция по
репетитору, партиал секции.
"""

import re
from datetime import UTC, datetime, timedelta

from app.database import SessionLocal
from app.finance.models.account_operation import AccountOperation
from app.finance.models.forecast_snapshot import ForecastSnapshot
from app.tutor.services.clock import utcnow

NBSP = "\u00a0"

PASSWORD = "Секретный-Пароль-2"


def _login(client, tutor_factory, email="forecaster@example.com", name="Прогнозов"):
    """Репетитор с зоной UTC (заводское умолчание) и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _charge(student_id: str, amount: int, when) -> None:
    """Списание за проведённый урок напрямую в БД (это и есть факт)."""
    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="lesson",
                amount=amount,
                occurred_at=when,
            )
        )
        session.commit()


def _payment(student_id: str, amount: int, when) -> None:
    """Оплаченный платёж напрямую в БД (предоплата на балансе ученика)."""
    with SessionLocal() as session:
        session.add(
            AccountOperation(
                student_id=student_id,
                kind="payment",
                amount=amount,
                status="paid",
                method="card",
                occurred_at=when,
            )
        )
        session.commit()


def _next_month_start() -> datetime:
    """Первое число следующего месяца в UTC — точка отсчёта плана."""
    today = utcnow()
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return datetime(year, month, 1, 12, 0, tzinfo=UTC)


def _forecast_section(html: str) -> str:
    """Разметка вкладки «Прогноз» — без сводки и карточки балансов.

    Внешняя секция закрывается `</section>` в начале строки, а карточки
    внутри сдвинуты отступом — по этому признаку и режем, иначе
    нежадный шаблон остановился бы на первой же карточке.
    """
    match = re.search(
        r'<section class="fin-forecast".*?\n</section>',
        html,
        flags=re.S,
    )
    assert match, "нет секции прогноза"
    return match.group(0)


def _metric(section: str, key: str) -> str:
    """Разметка одной карточки-метрики по её ключу."""
    match = re.search(
        rf'<section class="card fin-metric fin-metric--{key}".*?</section>',
        section,
        flags=re.S,
    )
    assert match, f"нет карточки {key}"
    return match.group(0)


def test_forecast_tab_is_not_stub(client, tutor_factory):
    """Вкладка больше не заглушка: месяц, действия и карточки-метрики."""
    _login(client, tutor_factory)

    section = _forecast_section(client.get("/tutor/finance?tab=forecast").text)

    assert "Раздел в разработке" not in section
    for label in (
        "Факт",
        "По календарю",
        "Не в расписании",
        "Итого за месяц",
        "Деньги к поступлению",
    ):
        assert label in section
    assert "Скачать CSV" in section
    assert "Зафиксировать прогноз" in section
    # Прогноз по педагогам, ЗП и маржа не считаются (решение владельца).
    assert "По педагогам" not in section
    assert "ЗП" not in section
    assert "Маржа" not in section


def test_forecast_fact_sums_lesson_charges(
    client, tutor_factory, student_factory
):
    """Факт — списания за проведённые уроки текущего месяца, и только они."""
    tutor_id = _login(client, tutor_factory)
    student = student_factory(tutor_id=tutor_id, first_name="Аня")
    now = utcnow()
    _charge(student, 1200, now)
    _charge(student, 800, now)
    # Платёж — не выручка за уроки: в факт не входит.
    _payment(student, 5000, now)

    section = _forecast_section(client.get("/tutor/finance?tab=forecast").text)

    fact = _metric(section, "fact")
    assert f"2{NBSP}000{NBSP}₽" in fact
    assert "Уже списано" in fact


def test_forecast_calendar_counts_group_members(
    client, tutor_factory, student_factory, group_factory, group_member_factory,
    lesson_factory,
):
    """По календарю: цена группового урока — сумма цен участников."""
    tutor_id = _login(client, tutor_factory)
    group_id = group_factory(tutor_id=tutor_id, price_per_lesson=1000)
    first = student_factory(tutor_id=tutor_id, first_name="Аня")
    second = student_factory(tutor_id=tutor_id, first_name="Боря")
    group_member_factory(group_id=group_id, student_id=first)
    # У второго участника своя цена — она перекрывает цену группы.
    group_member_factory(group_id=group_id, student_id=second, price_override=1500)
    lesson_factory(group_id=group_id, price=None, status="planned",
                   starts_at=_next_month_start())

    section = _forecast_section(
        client.get("/tutor/finance?tab=forecast&month=next").text
    )

    calendar = _metric(section, "calendar")
    # 1 000 (по цене группы) + 1 500 (своя цена) = 2 500.
    assert f"2{NBSP}500{NBSP}₽" in calendar
    assert "1 занятие до конца месяца" in calendar

    # Расшифровка по ученикам: оба участника названы своими суммами.
    assert "Аня" in section
    assert "Боря" in section
    assert f"1{NBSP}500{NBSP}₽" in section


def test_forecast_unscheduled_students(
    client, tutor_factory, student_factory, lesson_factory
):
    """Ученик с занятиями в прошлом, но без плана — попадает в ожидание."""
    tutor_id = _login(client, tutor_factory)
    # «Не в расписании» — про действующих учеников: заводской статус
    # фабрики «new» сюда не годится, нужен «active».
    student = student_factory(tutor_id=tutor_id, first_name="Петя", status="active")
    # Четыре занятия за последние четыре недели — темп «раз в неделю».
    # Дни выбраны внутри окна: занятие ровно 28 дней назад из него уже
    # выпадает (окно — `[сейчас − 28 дней, сейчас)`).
    for days_ago in (3, 10, 17, 24):
        _charge(student, 1200, utcnow() - timedelta(days=days_ago))

    # В следующем месяце у него занятия нет — он «не в расписании».
    planned_student = student_factory(tutor_id=tutor_id, first_name="Вера")
    lesson_factory(student_id=planned_student, price=2000, status="planned",
                   starts_at=_next_month_start())

    section = _forecast_section(
        client.get("/tutor/finance?tab=forecast&month=next").text
    )

    unscheduled = _metric(section, "unscheduled")
    assert "Петя" in section
    assert "за 4 недели 4 зан." in section
    # Ожидание не пустое, а «Вера» — в календаре, а не здесь.
    detail = re.search(
        r'aria-label="Не в расписании">\s*<h2 class="fin-forecast__detail-title".*?</section>',
        section,
        flags=re.S,
    ).group(0)
    assert "Петя" in detail
    assert "Вера" not in detail
    assert "₽" in unscheduled


def test_forecast_total_is_fact_plus_calendar_plus_expectation(
    client, tutor_factory, student_factory, lesson_factory
):
    """Итого: нижняя граница — факт + календарь, верхняя — плюс ожидание."""
    tutor_id = _login(client, tutor_factory)
    student = student_factory(tutor_id=tutor_id, first_name="Аня")
    now = utcnow()
    _charge(student, 1000, now)

    planned = student_factory(tutor_id=tutor_id, first_name="Боря")
    lesson_factory(student_id=planned, price=2000, status="planned",
                   starts_at=_next_month_start())

    # Текущий месяц: факт есть, календарь — что осталось до конца месяца.
    section = _forecast_section(client.get("/tutor/finance?tab=forecast").text)
    total = _metric(section, "total")
    # Нижняя граница не меньше факта — прогноз не занижает уже заработанное.
    assert f"1{NBSP}000{NBSP}₽" in total or f"2{NBSP}000{NBSP}₽" in total
    assert "Факт + календарь" in total


def test_forecast_receive_subtracts_prepayment(
    client, tutor_factory, student_factory, lesson_factory
):
    """Деньги к поступлению: будущие списания минус предоплата на балансах."""
    tutor_id = _login(client, tutor_factory)
    student = student_factory(tutor_id=tutor_id, first_name="Аня")
    # Предоплата 3 000 на балансе — эти деньги уже внесены.
    _payment(student, 3000, utcnow())
    lesson_factory(student_id=student, price=1000, status="planned",
                   starts_at=_next_month_start())

    section = _forecast_section(
        client.get("/tutor/finance?tab=forecast&month=next").text
    )

    receive = _metric(section, "receive")
    # 1 000 будущих списаний − 3 000 предоплаты → 0, а не отрицательное число.
    assert f"0{NBSP}₽" in receive
    assert f"предоплата на балансах: 3{NBSP}000{NBSP}₽" in receive


def test_forecast_warns_about_unpriced_lesson(
    client, tutor_factory, student_factory, lesson_factory
):
    """Урок без цены в прогноз не входит — о нём говорит предупреждение."""
    tutor_id = _login(client, tutor_factory)
    student = student_factory(tutor_id=tutor_id, first_name="Аня")
    lesson_factory(student_id=student, price=None, status="planned",
                   starts_at=_next_month_start())

    section = _forecast_section(
        client.get("/tutor/finance?tab=forecast&month=next").text
    )

    assert "На что обратить внимание" in section
    assert "без цены не вошли в прогноз" in section
    # Пустой календарь — честное сообщение вместо нуля без объяснения.
    assert "Запланированных уроков до конца месяца нет" in _metric(section, "calendar")


def test_forecast_pin_creates_snapshot_and_compares(
    client, tutor_factory, student_factory, lesson_factory
):
    """Фиксация сохраняет снимок, а карточка сравнивает его с фактом."""
    tutor_id = _login(client, tutor_factory)
    student = student_factory(tutor_id=tutor_id, first_name="Аня")
    month_start = _next_month_start()
    lesson_factory(student_id=student, price=1000, status="planned",
                   starts_at=month_start)

    response = client.post(
        "/tutor/finance/forecast/pin?month=next", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/finance?tab=forecast&month=next"

    with SessionLocal() as session:
        snapshot = session.query(ForecastSnapshot).one()
        assert snapshot.tutor_id == tutor_id
        assert (snapshot.revenue_low, snapshot.revenue_high) == (1000, 1000)

    # Факт упал ниже прогноза: списание 400 вместо ожидаемых 1 000.
    _charge(student, 400, month_start + timedelta(days=1))

    section = _forecast_section(
        client.get("/tutor/finance?tab=forecast&month=next").text
    )
    assert "Прогноз vs факт — на сегодня" in section
    assert "зафиксирован вручную" in section
    assert "ниже прогноза" in section
    assert f"{NBSP}−60,0 %" in section or "−60,0 %" in section
    assert f"400{NBSP}₽" in section


def test_forecast_pin_twice_updates_snapshot(client, tutor_factory):
    """Повторная фиксация того же месяца заменяет снимок, а не плодит строки."""
    _login(client, tutor_factory)

    for _ in range(2):
        assert client.post(
            "/tutor/finance/forecast/pin?month=next", follow_redirects=False
        ).status_code == 303

    with SessionLocal() as session:
        assert session.query(ForecastSnapshot).count() == 1


def test_forecast_without_snapshot_has_no_comparison_card(client, tutor_factory):
    """Без фиксации карточки сравнения нет: сравнивать не с чем."""
    _login(client, tutor_factory)
    section = _forecast_section(client.get("/tutor/finance?tab=forecast").text)
    assert "Прогноз vs факт" not in section


def test_forecast_csv_download(client, tutor_factory, student_factory, lesson_factory):
    """CSV отдаётся файлом и содержит сводку и строки по ученикам."""
    tutor_id = _login(client, tutor_factory)
    student = student_factory(tutor_id=tutor_id, first_name="Аня")
    lesson_factory(student_id=student, price=1000, status="planned",
                   starts_at=_next_month_start())

    response = client.get("/tutor/finance/forecast.csv?month=next")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8-sig")
    assert "Итого за месяц" in text
    assert "Аня" in text


def test_forecast_month_switch_and_garbage(client, tutor_factory):
    """Мусор в `month` — текущий месяц; селектор помечает выбранный."""
    _login(client, tutor_factory)

    html = client.get("/tutor/finance?tab=forecast&month=99").text
    assert re.search(r'<option value="current" selected>', html)
    assert not re.search(r'<option value="next" selected>', html)

    next_html = client.get("/tutor/finance?tab=forecast&month=next").text
    assert re.search(r'<option value="next" selected>', next_html)


def test_forecast_period_switch_keeps_month(client, tutor_factory):
    """Смена периода сводки на вкладке не сбрасывает выбранный месяц."""
    _login(client, tutor_factory)
    html = client.get("/tutor/finance?tab=forecast&month=next").text
    assert 'name="month" value="next"' in html

    plain = client.get("/tutor/finance?tab=all").text
    assert 'name="month"' not in plain


def test_forecast_isolation_by_tutor(
    client, tutor_factory, student_factory, lesson_factory
):
    """Чужие уроки и списания не попадают в прогноз вошедшего репетитора."""
    tutor_id = _login(client, tutor_factory)
    mine = student_factory(tutor_id=tutor_id, first_name="Аня")
    lesson_factory(student_id=mine, price=1000, status="planned",
                   starts_at=_next_month_start())

    stranger_id = tutor_factory(name="Чужой", email="stranger@example.com")
    stranger_student = student_factory(tutor_id=stranger_id, first_name="Никита")
    lesson_factory(student_id=stranger_student, price=90000, status="planned",
                   starts_at=_next_month_start())
    _charge(stranger_student, 70000, utcnow())

    section = _forecast_section(
        client.get("/tutor/finance?tab=forecast&month=next").text
    )

    assert "Никита" not in section
    assert f"90{NBSP}000{NBSP}₽" not in section
    assert f"70{NBSP}000{NBSP}₽" not in section
    assert "Аня" in section


def test_forecast_partial_refresh_endpoint(
    client, tutor_factory, student_factory, lesson_factory
):
    """Партиал `/tutor/finance/operations` строит прогноз так же, как страница."""
    tutor_id = _login(client, tutor_factory)
    student = student_factory(tutor_id=tutor_id, first_name="Аня")
    lesson_factory(student_id=student, price=1000, status="planned",
                   starts_at=_next_month_start())

    partial = client.get(
        "/tutor/finance/operations?period=month&tab=forecast&month=next"
    ).text

    assert 'id="finance-operations"' in partial
    assert "Итого за месяц" in partial
    assert "Аня" in partial
