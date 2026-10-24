"""Тесты панели «Отпуск и выходные»: доступ, разметка, CRUD через HTTP.

Путь тот же, что у пользователя: GET фрагмента панели, POST формы с
заголовком htmx (`HX-Request: true`) и без него (ответ 303). Разметка
ищется по тексту и атрибутам, а не по внутренностям функций.
"""

import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.unavailability.models.unavailability import TutorUnavailability

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="unavail@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "unavail@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _marks() -> list[TutorUnavailability]:
    """Все отметки БД."""
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(TutorUnavailability).order_by(TutorUnavailability.created_at)
            )
        )


def _period_form(**extra) -> dict:
    """Валидная форма периода: отпуск 26.10–30.10.2026."""
    data = {
        "mode": "period",
        "reason": "vacation",
        "start_date": "2026-10-26",
        "end_date": "2026-10-30",
    }
    data.update(extra)
    return data


# --------------------------------------------------------------------------
# 3.1 Доступ: сессия обязательна
# --------------------------------------------------------------------------


def test_panel_requires_session(client):
    """Без входа панель не отдаётся — редирект на /tutor/login."""
    response = client.get("/tutor/unavailability", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_panel_opens_with_session(owner, client):
    """С сессией панель открывается в #modal-фрагменте."""
    response = client.get("/tutor/unavailability")
    assert response.status_code == 200
    assert "Отпуск и выходные" in response.text
    assert 'id="unavailability-panel"' in response.text


def test_create_without_session_redirects_and_writes_nothing(client):
    """POST без сессии не создаёт отметку и редиректит на вход."""
    response = client.post(
        "/tutor/unavailability", data=_period_form(), follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert _marks() == []


# --------------------------------------------------------------------------
# 3.2 Разметка панели
# --------------------------------------------------------------------------


def test_panel_has_mode_switch_and_both_field_sets(owner, client):
    """Переключатель режима и поля обоих режимов есть в разметке."""
    page = client.get("/tutor/unavailability").text

    # Переключатель режима: оба значения radio.
    assert 'name="mode" value="period"' in page
    assert 'name="mode" value="weekday"' in page
    assert "Постоянный выходной" in page

    # Поля периода.
    assert 'id="un-reason"' in page
    assert 'id="un-start"' in page
    assert 'id="un-end"' in page
    # Поля постоянного выходного.
    assert 'id="un-weekday"' in page
    assert 'id="un-until"' in page

    # Блок «Уже отмечено» и кнопка добавления.
    assert "Уже отмечено" in page
    assert re.search(r'<button[^>]*type="submit"[\s\S]{0,200}?Добавить', page)


def test_panel_empty_state(owner, client):
    """Пустой список: пояснение, что отметок пока нет."""
    page = client.get("/tutor/unavailability").text
    assert "Отметок пока нет." in page
    # Свёртка прошедших не рисуется, пока прошедших нет.
    assert "Показать прошедшие" not in page


def test_panel_form_posts_to_itself_and_swaps_outer_html(owner, client):
    """Форма — цель своего свопа: успех возвращает панель (design.md D8)."""
    page = client.get("/tutor/unavailability").text
    form = re.search(r"<form[^>]*hx-post=\"/tutor/unavailability\"[^>]*>", page)
    assert form, "Формы панели нет в разметке"
    assert 'hx-target="#unavailability-panel"' in form.group(0)
    assert 'hx-swap="outerHTML"' in form.group(0)


# --------------------------------------------------------------------------
# 3.5 Поведение панели через HTTP
# --------------------------------------------------------------------------


def test_create_period_mark_returns_panel_with_saved_mark(owner, client):
    """Создание периода: панель возвращается с отметкой в списке."""
    response = client.post("/tutor/unavailability", data=_period_form(), headers=HTMX)

    assert response.status_code == 200
    assert "Отпуск" in response.text
    assert "26.10 – 30.10" in response.text
    assert response.headers["HX-Trigger"] == "unavailability-saved"

    (mark,) = _marks()
    assert mark.mode == "period"
    assert mark.reason == "vacation"
    assert mark.start_date == date(2026, 10, 26)
    assert mark.end_date == date(2026, 10, 30)


def test_create_weekday_mark(owner, client):
    """Создание постоянного выходного: причина «Выходной», срок бессрочный."""
    response = client.post(
        "/tutor/unavailability",
        data={"mode": "weekday", "weekday": "5"},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert "Выходной" in response.text
    assert "сб, бессрочно" in response.text
    assert response.headers["HX-Trigger"] == "unavailability-saved"

    (mark,) = _marks()
    assert mark.mode == "weekday"
    assert mark.weekday == 5
    assert mark.reason == "dayoff"


def test_create_with_end_before_start_shows_error_and_keeps_values(owner, client):
    """«Конец раньше начала»: ошибка, отметка не создана, поля сохранены."""
    response = client.post(
        "/tutor/unavailability",
        data=_period_form(start_date="2026-10-30", end_date="2026-10-26"),
        headers=HTMX,
    )

    assert response.status_code == 200
    assert "Последний день не раньше первого." in response.text
    # Присланные значения вернулись в форму, а не сброшены.
    assert 'value="2026-10-30"' in response.text
    assert 'value="2026-10-26"' in response.text
    assert _marks() == []
    assert "HX-Trigger" not in response.headers


def test_create_with_invalid_reason_shows_error(owner, client):
    """Причина вне закрытого списка — ошибка, отметка не создана."""
    response = client.post(
        "/tutor/unavailability",
        data=_period_form(reason="holiday"),
        headers=HTMX,
    )

    assert "Выберите причину недоступности." in response.text
    assert _marks() == []


def test_create_without_js_redirects_to_calendar(owner, client):
    """Без HX-Request ответ — 303 на календарь (форма работает без JS)."""
    response = client.post(
        "/tutor/unavailability", data=_period_form(), follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/calendar"
    assert len(_marks()) == 1


def test_change_end_changes_only_span(owner, client, unavailability_factory):
    """«Изменить срок» меняет только последний день (design.md D9)."""
    mark_id = unavailability_factory(
        tutor_id=owner,
        start_date=date(2026, 10, 26),
        end_date=date(2026, 10, 30),
    )

    response = client.post(
        f"/tutor/unavailability/{mark_id}/end",
        data={"new_end": "2026-11-06"},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert "26.10 – 06.11" in response.text
    assert response.headers["HX-Trigger"] == "unavailability-saved"

    (mark,) = _marks()
    assert mark.end_date == date(2026, 11, 6)
    assert mark.start_date == date(2026, 10, 26)
    assert mark.reason == "vacation"


def test_change_end_for_weekday_mark(owner, client, unavailability_factory):
    """У постоянного выходного тем же способом правится «Действует по»."""
    mark_id = unavailability_factory(tutor_id=owner, mode="weekday", weekday=6)

    response = client.post(
        f"/tutor/unavailability/{mark_id}/end",
        data={"new_end": "2026-12-31"},
        headers=HTMX,
    )

    assert response.status_code == 200
    assert "вс, по 31.12" in response.text
    (mark,) = _marks()
    assert mark.until_date == date(2026, 12, 31)


def test_change_end_before_start_shows_error(owner, client, unavailability_factory):
    """Некорректный новый срок: панель с ошибкой, срок не изменён."""
    mark_id = unavailability_factory(
        tutor_id=owner,
        start_date=date(2026, 10, 26),
        end_date=date(2026, 10, 30),
    )

    response = client.post(
        f"/tutor/unavailability/{mark_id}/end",
        data={"new_end": "2026-10-20"},
        headers=HTMX,
    )

    assert "Последний день не раньше первого." in response.text
    (mark,) = _marks()
    assert mark.end_date == date(2026, 10, 30)


def test_delete_removes_mark(owner, client, unavailability_factory):
    """«Снять» удаляет отметку, панель возвращается с пустым списком."""
    mark_id = unavailability_factory(tutor_id=owner)

    response = client.post(
        f"/tutor/unavailability/{mark_id}/delete", headers=HTMX
    )

    assert response.status_code == 200
    assert "Отметок пока нет." in response.text
    assert response.headers["HX-Trigger"] == "unavailability-saved"
    assert _marks() == []


def test_panel_lists_marks_with_both_buttons(owner, client, unavailability_factory):
    """У отметки в списке есть «Изменить срок» и «Снять»."""
    unavailability_factory(tutor_id=owner)
    page = client.get("/tutor/unavailability").text

    assert "Изменить срок" in page
    assert "Снять" in page
    assert "Точно снять?" in page
    assert 'name="new_end"' in page


def test_panel_hides_past_marks_under_details(
    owner, client, unavailability_factory
):
    """Прошедшая отметка — под «Показать прошедшие», будущая — в списке."""
    unavailability_factory(
        tutor_id=owner,
        start_date=date(2020, 1, 6),
        end_date=date(2020, 1, 10),
    )
    unavailability_factory(
        tutor_id=owner,
        start_date=date(2099, 1, 5),
        end_date=date(2099, 1, 9),
    )

    page = client.get("/tutor/unavailability").text
    assert "Показать прошедшие" in page
    # Прошедшая строка помечена классом и лежит внутри свёртки.
    past = re.search(r'<details class="un-past">.*?</details>', page, re.S)
    assert past, "Свёртки прошедших нет"
    assert "06.01 – 10.01" in past.group(0)
    # Будущая — до свёртки.
    assert page.index("05.01 – 09.01") < page.index('<details class="un-past">')


def test_panel_success_button_is_restored_after_save(owner, client):
    """Кнопка успеха возвращается в обычное состояние (design.md D8).

    Без сброса панель оставалась бы с неактивной зелёной кнопкой
    «Успешно сохранено» — повторно добавить отметку было бы нельзя.
    """
    response = client.post("/tutor/unavailability", data=_period_form(), headers=HTMX)
    page = response.text

    # Ответ несёт кнопку в состоянии успеха и маркер для сброса.
    assert "btn--success" in page
    assert "Успешно сохранено" in page
    assert "data-un-save" in page

    js = (ROOT / "app" / "static" / "calendar.js").read_text(encoding="utf-8")
    assert 'querySelectorAll("[data-un-save]")' in js
    assert 'button.textContent = UN_IDLE_LABEL' in js
    assert 'UN_IDLE_LABEL = "Добавить"' in js
    # Сброс вешается на подмену области htmx.
    assert 'restoreUnavailabilityButton(event.target)' in js


def test_panel_reason_and_span_labels_come_from_template_helpers(owner, client):
    """Подписи причины и срока доступны в шаблоне без импорта вьюх (задача 3.3).

    Функции зарегистрированы в общем Jinja-окружении через
    `register_template_helpers()`: шаблон не форматирует бизнес-данные сам
    (правило AGENTS.md).
    """
    from app.templating import templates

    for name in (
        "unavailability_reason_label",
        "unavailability_span",
        "unavailability_weekday_label",
    ):
        assert name in templates.env.globals, f"нет хелпера {name}"

    # Хелперы действительно отрабатывают в разметке панели: подпись причины
    # и форматированный срок приходят из них, а не из шаблона.
    client.post("/tutor/unavailability", data=_period_form(), headers=HTMX)
    page = client.get("/tutor/unavailability").text
    assert re.search(r'class="un-mark__reason">\s*Отпуск\s*<', page)
    assert re.search(r'class="un-mark__span">\s*26\.10 – 30\.10\s*<', page)


def test_panel_does_not_show_foreign_marks(
    owner, client, tutor_factory, unavailability_factory
):
    """Изоляция: в списке только отметки вошедшего репетитора."""
    stranger_id = tutor_factory()
    unavailability_factory(
        tutor_id=stranger_id,
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 6),
    )

    page = client.get("/tutor/unavailability").text
    assert "02.11 – 06.11" not in page
    assert "Отметок пока нет." in page


def test_foreign_mark_cannot_be_changed_or_deleted(
    owner, client, tutor_factory, unavailability_factory
):
    """Чужая отметка недоступна: 404 на изменение и снятие, запись цела."""
    stranger_id = tutor_factory()
    mark_id = unavailability_factory(
        tutor_id=stranger_id,
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 6),
    )

    end = client.post(
        f"/tutor/unavailability/{mark_id}/end",
        data={"new_end": "2026-11-20"},
        headers=HTMX,
        follow_redirects=False,
    )
    delete = client.post(
        f"/tutor/unavailability/{mark_id}/delete",
        headers=HTMX,
        follow_redirects=False,
    )

    assert end.status_code == 404
    assert delete.status_code == 404
    (mark,) = _marks()
    assert mark.end_date == date(2026, 11, 6)


def test_missing_mark_is_404(owner, client):
    """Несуществующая отметка — 404, как и чужая."""
    end = client.post(
        "/tutor/unavailability/no-such-mark/end",
        data={"new_end": "2026-11-20"},
        headers=HTMX,
        follow_redirects=False,
    )
    delete = client.post(
        "/tutor/unavailability/no-such-mark/delete",
        headers=HTMX,
        follow_redirects=False,
    )
    assert end.status_code == 404
    assert delete.status_code == 404


def test_mark_past_depends_on_tutor_zone_today(
    client, tutor_factory, unavailability_factory, monkeypatch
):
    """Спека (задача 8.2): «сегодня» для отметки — в зоне педагога.

    Один серверный момент (22.10 21:30 UTC) и одна и та же отметка со
    сроком по 22.10. У педагога в UTC+04 это уже 23.10 — срок истёк, отметка
    прошедшая. У педагога в EDT (UTC−4) ещё 22.10 17:30 — отметка действует.
    Значит, признак прошедшей считается по календарю педагога, а не сервера.
    """
    fixed = datetime(2026, 10, 22, 21, 30, tzinfo=UTC)
    monkeypatch.setattr("app.common.services.tutor_time.utcnow", lambda: fixed)

    pages = {}
    for email, zone in (
        ("unavail-tz-east@example.com", "Europe/Ulyanovsk"),
        ("unavail-tz-west@example.com", "America/New_York"),
    ):
        tutor_id = tutor_factory(email=email, password=PASSWORD, timezone=zone)
        unavailability_factory(
            tutor_id=tutor_id,
            start_date=date(2026, 10, 19),
            end_date=date(2026, 10, 22),
        )
        client.post(
            "/tutor/login",
            data={"email": email, "password": PASSWORD},
            follow_redirects=False,
        )
        pages[zone] = client.get("/tutor/unavailability").text

    # UTC+04: местное «сегодня» уже 23.10 — срок по 22.10 истёк.
    assert "un-mark--past" in pages["Europe/Ulyanovsk"]
    # EDT: местное «сегодня» ещё 22.10 — отметка действует, прошедших нет.
    assert "un-mark--past" not in pages["America/New_York"]
    assert "Показать прошедшие" not in pages["America/New_York"]
