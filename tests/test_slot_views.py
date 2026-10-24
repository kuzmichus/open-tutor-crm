"""Тесты вьюх окон: диалог, создание, пачка, перенос, удаление, изоляция.

Проверяется поведение через HTTP — теми же маршрутами и полями формы,
что у пользователя (правило AGENTS.md). Разметка ищется по тексту и
атрибутам, а не по внутренностям функций: тест не должен ломаться от
переименования переменной в шаблоне.
"""

from datetime import UTC, datetime
from pathlib import Path
import re

import pytest

from app.database import SessionLocal
from app.slot.models.slot import Slot

PASSWORD = "Секретный-Пароль-1"

_STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "static"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id.

    Зона задана явно: иначе тесты зависели бы от системной зоны машины,
    а настенное время формы должно совпадать с хранимым UTC.
    """
    tutor_id = tutor_factory(
        email="slot-owner@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "slot-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id



def _slots(tutor_id: str) -> list[Slot]:
    """Все окна репетитора из БД."""
    with SessionLocal() as session:
        return list(session.query(Slot).filter_by(tutor_id=tutor_id).all())


# --------------------------------------------------------------------------
# 4.1 Создание, отказ без сессии, удаление
# --------------------------------------------------------------------------


def test_create_single_slot_via_form(client, owner):
    """Форма одного окна создаёт строку в БД с полями из формы."""
    response = client.post(
        "/tutor/slots",
        data={
            "date": "2026-10-14",
            "time": "14:00",
            "duration_min": "45",
            "is_public": "on",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert response.headers["HX-Trigger"] == "slot-saved"

    slots = _slots(owner)
    assert len(slots) == 1
    assert slots[0].starts_at.replace(tzinfo=UTC) == datetime(2026, 10, 14, 14, 0, tzinfo=UTC)
    assert slots[0].duration_min == 45
    assert slots[0].is_public is True


def test_create_slot_without_js_redirects_to_calendar(client, owner):
    """Без `HX-Request` POST отвечает 303 на календарь: форма работает и без JS."""
    response = client.post(
        "/tutor/slots",
        data={"date": "2026-10-14", "time": "14:00", "duration_min": "40"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/calendar"
    assert len(_slots(owner)) == 1


def test_create_slot_requires_session(client):
    """Без сессии создание перенаправляет на вход и ничего не пишет."""
    response = client.post(
        "/tutor/slots",
        data={"date": "2026-10-14", "time": "14:00", "duration_min": "40"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_create_slot_with_bad_duration_shows_error(client, owner):
    """Длительность вне закрытого списка отклоняется с сообщением."""
    response = client.post(
        "/tutor/slots",
        data={"date": "2026-10-14", "time": "14:00", "duration_min": "80"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Выберите длительность окна из списка." in response.text
    assert _slots(owner) == []


def test_create_slot_conflicting_with_lesson_is_rejected(
    client, owner, student_factory
):
    """Окно поверх урока не создаётся: причина — занятое время."""
    from app.lesson.models.lesson import Lesson

    student_id = student_factory(tutor_id=owner)
    with SessionLocal() as session:
        session.add(
            Lesson(
                student_id=student_id,
                type="individual",
                starts_at=datetime(2026, 10, 14, 14, 20, tzinfo=UTC),
                duration_min=40,
                status="planned",
            )
        )
        session.commit()

    response = client.post(
        "/tutor/slots",
        data={"date": "2026-10-14", "time": "14:00", "duration_min": "40"},
        headers={"HX-Request": "true"},
    )

    assert "На это время уже стоит урок." in response.text
    assert _slots(owner) == []


def test_create_duplicate_slot_is_rejected(client, owner, slot_factory):
    """Второе окно на то же время отклоняется, а не падает с 500."""
    slot_factory(owner, datetime(2026, 10, 14, 14, 0, tzinfo=UTC))

    response = client.post(
        "/tutor/slots",
        data={"date": "2026-10-14", "time": "14:00", "duration_min": "40"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "уже есть окно" in response.text or "уже существует" in response.text
    assert len(_slots(owner)) == 1


def test_delete_free_slot_removes_it(client, owner, slot_factory):
    """Свободное окно удаляется, событие обновляет неделю."""
    slot_id = slot_factory(owner, datetime(2026, 10, 14, 14, 0, tzinfo=UTC))

    response = client.post(
        f"/tutor/slots/{slot_id}/delete",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "slot-saved"
    assert _slots(owner) == []


def test_delete_slot_with_booking_is_rejected(client, owner, slot_factory):
    """Окно с активной бронью не удаляется: сначала бронь отменяется."""
    from app.booking.models.booking import Booking

    slot_id = slot_factory(owner, datetime(2026, 10, 14, 14, 0, tzinfo=UTC))
    with SessionLocal() as session:
        session.add(
            Booking(slot_id=slot_id, name="Мария", contact="+7 999 000-00-00")
        )
        session.commit()

    response = client.post(
        f"/tutor/slots/{slot_id}/delete",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "активная бронь" in response.text
    assert len(_slots(owner)) == 1


def test_move_slot_changes_only_start(client, owner, slot_factory):
    """Перенос меняет начало, длительность и публичность из формы."""
    slot_id = slot_factory(
        owner, datetime(2026, 10, 14, 14, 0, tzinfo=UTC), duration_min=40
    )

    response = client.post(
        f"/tutor/slots/{slot_id}",
        data={
            "date": "2026-10-15",
            "time": "10:00",
            "duration_min": "60",
            "is_public": "on",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "slot-saved"
    slots = _slots(owner)
    assert slots[0].starts_at.replace(tzinfo=UTC) == datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
    assert slots[0].duration_min == 60


def test_move_slot_onto_lesson_is_rejected(client, owner, student_factory, slot_factory):
    """Перенос на занятое время отклоняется, окно остаётся на месте."""
    from app.lesson.models.lesson import Lesson

    student_id = student_factory(tutor_id=owner)
    slot_id = slot_factory(owner, datetime(2026, 10, 14, 14, 0, tzinfo=UTC))
    with SessionLocal() as session:
        session.add(
            Lesson(
                student_id=student_id,
                type="individual",
                starts_at=datetime(2026, 10, 15, 10, 0, tzinfo=UTC),
                duration_min=40,
                status="planned",
            )
        )
        session.commit()

    response = client.post(
        f"/tutor/slots/{slot_id}",
        data={"date": "2026-10-15", "time": "10:00", "duration_min": "40"},
        headers={"HX-Request": "true"},
    )

    assert "На это время уже стоит урок." in response.text
    slots = _slots(owner)
    assert slots[0].starts_at.replace(tzinfo=UTC) == datetime(2026, 10, 14, 14, 0, tzinfo=UTC)


def test_slot_dialog_opens_for_owner(client, owner, slot_factory):
    """Диалог свободного окна отдаёт его параметры и действия.

    Окно в будущем: у прошедшего состояния «Время прошло» и действия
    «Записать ученика» нет — это отдельный тест ниже.
    """
    slot_id = slot_factory(owner, datetime(2027, 10, 14, 14, 0, tzinfo=UTC))

    response = client.get(f"/tutor/slots/{slot_id}")

    assert response.status_code == 200
    assert "Окно для записи" in response.text
    assert 'name="date"' in response.text
    assert "Сохранить" in response.text
    assert "Удалить" in response.text
    assert "Записать ученика" in response.text
    assert "Свободно" in response.text


def test_past_slot_dialog_has_no_booking_action(client, owner, slot_factory):
    """У прошедшего окна «Записать ученика» нет: время уже ушло."""
    slot_id = slot_factory(owner, datetime(2026, 10, 14, 14, 0, tzinfo=UTC))

    response = client.get(f"/tutor/slots/{slot_id}")

    assert response.status_code == 200
    assert "Время прошло" in response.text
    assert "Записать ученика" not in response.text


def test_foreign_slot_is_404(client, owner, tutor_factory, slot_factory):
    """Чужое окно отвечает как несуществующее — 404, а не 403."""
    other_id = tutor_factory(email="slot-other@example.com")
    foreign_slot = slot_factory(other_id, datetime(2026, 10, 14, 14, 0, tzinfo=UTC))

    assert client.get(f"/tutor/slots/{foreign_slot}").status_code == 404
    assert (
        client.post(
            f"/tutor/slots/{foreign_slot}/delete",
            headers={"HX-Request": "true"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/tutor/slots/{foreign_slot}",
            data={"date": "2026-10-15", "time": "10:00", "duration_min": "40"},
            headers={"HX-Request": "true"},
        ).status_code
        == 404
    )


# --------------------------------------------------------------------------
# 4.2 Диалог: два режима и предпросмотр пачки
# --------------------------------------------------------------------------


def test_dialog_has_both_modes(client, owner):
    """Диалог создания содержит оба режима и их поля."""
    response = client.get("/tutor/slots/new")

    assert response.status_code == 200
    assert "Одно окно" in response.text
    assert "Несколько дней" in response.text
    # Поля режима «Несколько дней».
    assert 'name="date_from"' in response.text
    assert 'name="weekdays"' in response.text
    assert 'name="day_start"' in response.text
    assert 'name="gap_min"' in response.text
    # Переключатель публичности — в обоих режимах.
    assert response.text.count('name="is_public"') == 2


def test_dialog_prefills_date_and_time_from_calendar(client, owner):
    """`?date=` и `?time=` предзаполняют режим «Одно окно»."""
    response = client.get("/tutor/slots/new?date=2026-10-14&time=14:30")

    assert response.status_code == 200
    assert 'value="2026-10-14"' in response.text
    assert 'value="14:30"' in response.text


def test_batch_preview_counts_windows(client, owner):
    """Предпросмотр показывает «Будет создано окон» и времена дня."""
    response = client.get(
        "/tutor/slots/plan",
        params={
            "date_from": "2027-10-11",
            "date_to": "2027-10-11",
            "weekdays": "0",
            "day_start": "10:00",
            "day_end": "18:00",
            "duration_min": "40",
            "gap_min": "15",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Будет создано окон: 9" in response.text
    assert "10:00" in response.text
    assert "17:20" in response.text


def test_batch_preview_lists_skip_reasons(client, owner, student_factory):
    """Пропуск по уроку виден в предпросмотре с подписью причины."""
    from app.lesson.models.lesson import Lesson

    student_id = student_factory(tutor_id=owner)
    with SessionLocal() as session:
        session.add(
            Lesson(
                student_id=student_id,
                type="individual",
                starts_at=datetime(2027, 10, 11, 12, 45, tzinfo=UTC),
                duration_min=40,
                status="planned",
            )
        )
        session.commit()

    response = client.get(
        "/tutor/slots/plan",
        params={
            "date_from": "2027-10-11",
            "date_to": "2027-10-11",
            "weekdays": "0",
            "day_start": "10:00",
            "day_end": "18:00",
            "duration_min": "40",
            "gap_min": "15",
        },
        headers={"HX-Request": "true"},
    )

    assert "Будет создано окон: 8" in response.text
    assert "Пропущено окон: 1" in response.text
    assert "Занято уроком" in response.text


def test_batch_preview_shows_limit_error(client, owner):
    """Превышение лимита видно уже в предпросмотре."""
    response = client.get(
        "/tutor/slots/plan",
        params=[
            ("date_from", "2027-10-11"),
            ("date_to", "2027-10-21"),
            ("day_start", "08:00"),
            ("day_end", "18:00"),
            ("duration_min", "30"),
            ("gap_min", "0"),
            *[("weekdays", str(day)) for day in range(7)],
        ],
        headers={"HX-Request": "true"},
    )

    assert "не более 200 окон" in response.text


def test_batch_creates_windows_and_keeps_report_dialog_open(client, owner):
    """Создание пачки пишет окна и возвращает отчёт, не закрывая диалог.

    Отчёт приходит в том же ответе, поэтому событие недели рассылается
    ПОСЛЕ подмены: иначе подписка `slot-saved` закрыла бы диалог вместе
    с отчётом о пропусках. Найдено в браузере: отчёт обязан остаться
    видимым — иначе пользователь не узнает, сколько окон создано и что
    пропущено (спека slot-management, «Отчёт о пропущенных окнах»).
    """
    response = client.post(
        "/tutor/slots/batch",
        data={
            "date_from": "2027-10-11",
            "date_to": "2027-10-11",
            "weekdays": "0",
            "day_start": "10:00",
            "day_end": "11:20",
            "duration_min": "40",
            "gap_min": "0",
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger-After-Swap"] == "slot-saved"
    assert "HX-Trigger" not in response.headers
    assert "Создано окон: 2" in response.text
    assert len(_slots(owner)) == 2
    # Диалог с отчётом не подписан на собственное событие сохранения.
    assert '@slot-saved.window="close()"' not in response.text
    # Заголовок блока — «Отчёт», а не «Предпросмотр»: блок статичен,
    # иначе `hx-trigger="load"` перерисовал бы отчёт предпросмотром.
    assert "Отчёт" in response.text
    assert "Предпросмотр" not in response.text

def test_dialog_mode_forms_reprocess_htmx(client, owner):
    """Обе формы режимов инициализируют htmx после вставки `template x-if`.

    Найдено в браузере: `template x-if` вставляет форму уже после того, как
    htmx обработал своп, поэтому без явного `htmx.process($el)` атрибуты
    `hx-*` мёртвые и форма уходит нативным submit'ом (пачка вместо одного
    окна делала GET календаря).
    """
    response = client.get("/tutor/slots/new")

    assert response.status_code == 200
    assert response.text.count('x-init="window.htmx && window.htmx.process($el)"') == 2
    # Каждая из форм режимов несёт `hx-post` на свой маршрут.
    assert 'hx-post="/tutor/slots"' in response.text
    assert 'hx-post="/tutor/slots/batch"' in response.text

def test_slot_dialog_close_ignores_detached_root():
    """Закрытие устаревшего диалога не стирает свежий отчёт.

    Найдено в браузере: htmx подменяет диалог (`hx-swap="outerHTML"`), а
    Alpine снимает слушатели с удалённого узла отложенно. Подписка
    `slot-saved` уже выброшенного диалога успевала сработать на событии,
    которое htmx рассылает после подмены, и `modal.innerHTML = ""` стирал
    только что пришедший отчёт о созданной пачке. Защита — `isConnected`:
    закрывает только тот диалог, который сейчас в документе.
    """
    script = (_STATIC_DIR / "slots.js").read_text(encoding="utf-8")

    close = re.search(r"close: function \(\) \{(.*?)\n        \},", script, re.S)
    assert close, "В slots.js нет метода close() компонента slotDialog"
    body = close.group(1)
    assert "isConnected" in body, (
        "close() обязан проверять, что диалог ещё в документе: иначе "
        "устаревший компонент очистит #modal вместе с новым отчётом"
    )
    # Проверка стоит до очистки контейнера — иначе она бесполезна.
    # Комментарии вырезаны: в них упоминается сам `modal.innerHTML`, и
    # поиск по сырому тексту нашёл бы объяснение вместо кода.
    code = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    assert code.index("isConnected") < code.index("innerHTML")

def test_slot_actions_tell_htmx_not_to_swap(client, owner, slot_factory):
    """Успешные действия окна закрывают диалог, не подменяя его.

    Найдено в браузере: событие `slot-saved` htmx рассылает ДО подмены,
    обработчик закрывает диалог и очищает `#modal`, а подмена пустым телом
    шла уже в отсоединённый узел — `htmx:swapError` и ошибка в консоли.
    `HX-Reswap: none` оставляет DOM закрытию, а не htmx.
    """
    slot_id = slot_factory(owner, datetime(2026, 10, 14, 9, 0, tzinfo=UTC))

    responses = [
        client.post(
            "/tutor/slots",
            data={"date": "2026-10-14", "time": "08:00", "duration_min": "40"},
            headers={"HX-Request": "true"},
        ),
        client.post(
            f"/tutor/slots/{slot_id}",
            data={"date": "2026-10-15", "time": "10:00", "duration_min": "40"},
            headers={"HX-Request": "true"},
        ),
        client.post(
            f"/tutor/slots/{slot_id}/delete",
            headers={"HX-Request": "true"},
        ),
    ]

    for response in responses:
        assert response.status_code == 200
        assert response.text == ""
        assert response.headers["HX-Trigger"] == "slot-saved"
        assert response.headers["HX-Reswap"] == "none"

def test_batch_over_limit_creates_nothing(client, owner):
    """Пачка сверх лимита не создаёт ни одного окна."""
    response = client.post(
        "/tutor/slots/batch",
        data={
            "date_from": "2027-10-11",
            "date_to": "2027-10-21",
            "day_start": "08:00",
            "day_end": "18:00",
            "duration_min": "30",
            "gap_min": "0",
            # Повторяющееся поле: список кодируется несколькими значениями.
            "weekdays": [str(day) for day in range(7)],
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "не более 200 окон" in response.text
    assert _slots(owner) == []

