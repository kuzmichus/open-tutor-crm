"""Тесты брони: заявка, подтверждение, отклонение, отмена, изоляция.

Проверяется поведение через HTTP — теми же маршрутами и полями формы, что
у пользователя (правило AGENTS.md). Состояние проверяется по БД и по
разметке диалога окна: тест не должен ломаться от переименования
внутренней переменной.
"""

from datetime import UTC, datetime

import pytest

from app.database import SessionLocal
from app.slot.models.slot import Slot

PASSWORD = "Секретный-Пароль-1"

# Будущее время: «сегодня» в проекте — 23.10.2026, и окно в 2026 году
# получило бы состояние `past`, а заявка на прошедшее окно отклоняется.
FUTURE = datetime(2027, 10, 14, 14, 0, tzinfo=UTC)

@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор с зоной UTC, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(
        email="booking-owner@example.com", password=PASSWORD, timezone="UTC"
    )
    client.post(
        "/tutor/login",
        data={"email": "booking-owner@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id

def _get(model, entity_id):
    """Строка из БД по id (в новой сессии, чтобы видеть коммит)."""
    with SessionLocal() as session:
        return session.get(model, entity_id)

def _count(model) -> int:
    """Сколько строк модели в БД."""
    with SessionLocal() as session:
        return session.query(model).count()

# --------------------------------------------------------------------------
# 5.1 Заявка в статусе «Ожидает подтверждения»
# --------------------------------------------------------------------------

def test_request_booking_creates_pending_without_student_or_lesson(owner, slot_factory):
    """Заявка на свободное окно: бронь ожидает, ученик и урок не созданы."""
    from app.booking.models.booking import Booking
    from app.booking.services.booking_form import parse_booking_form
    from app.booking.services.booking_writer import request_booking
    from app.common.services.tutor_time import now_utc
    from app.lesson.models.lesson import Lesson
    from app.student.models.student import Student

    slot_id = slot_factory(owner)
    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        params, errors = parse_booking_form(
            {"name": "Мария Петрова", "contact": "+7 999 000-00-00"}
        )
        assert errors == []
        booking, errors = request_booking(session, slot, params, now=now_utc())

    assert errors == []
    assert booking.status == "pending"
    assert booking.student_id is None
    assert booking.lesson_id is None
    assert _count(Student) == 0
    assert _count(Lesson) == 0
    assert _count(Booking) == 1

@pytest.mark.parametrize(
    ("slot_kwargs", "message"),
    [
        (
            {"starts_at": datetime(2026, 1, 10, 10, 0, tzinfo=UTC)},
            "Время этого окна уже прошло.",
        ),
        ({"is_public": False}, "Это окно недоступно для записи."),
    ],
    ids=["past-slot", "private-slot"],
)
def test_request_booking_is_rejected(owner, slot_kwargs, message, slot_factory):
    """Прошедшее или приватное окно заявку не принимает."""
    from app.booking.services.booking_form import BookingParams
    from app.booking.services.booking_writer import request_booking
    from app.common.services.tutor_time import now_utc

    slot_id = slot_factory(owner, **slot_kwargs)
    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        booking, errors = request_booking(
            session,
            slot,
            BookingParams(name="Мария", contact="+7 999 000-00-00"),
            now=now_utc(),
        )

    assert booking is None
    assert errors == [message]

def test_second_request_on_same_slot_is_rejected(owner, slot_factory, booking_factory):
    """Вторая заявка на окно с активной бронью не создаётся."""
    from app.booking.services.booking_form import BookingParams
    from app.booking.services.booking_writer import request_booking
    from app.common.services.tutor_time import now_utc

    slot_id = slot_factory(owner)
    booking_factory(slot_id)

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        booking, errors = request_booking(
            session,
            slot,
            BookingParams(name="Второй", contact="+7 999 111-11-11"),
            now=now_utc(),
        )

    assert booking is None
    assert errors == ["Это время уже занято. Выберите другое окно."]
    assert _count(_booking_model()) == 1

def _booking_model():
    from app.booking.models.booking import Booking

    return Booking

# --------------------------------------------------------------------------
# 5.2 Подтверждение: ученик и урок
# --------------------------------------------------------------------------

def test_confirm_matches_existing_student_by_name_and_phone(client, owner, student_factory, slot_factory, booking_factory):
    """Совпадение по имени и телефону использует существующего ученика.

    Формат телефона сравнивается примитивно — «только цифры и ведущий `+`»
    (design D9). Поэтому бронь и карточка приведены к одному формату, а
    разделители (пробелы, дефисы) на совпадение не влияют.
    """
    from app.booking.models.booking import Booking
    from app.student.models.student import Student

    student_id = student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", phone="+7 999 000-00-00"
    )
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id, name="мария петрова", contact="+79990000000")

    response = client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "slot-saved"
    booking = _get(Booking, booking_id)
    assert booking.status == "confirmed"
    assert booking.student_id == student_id
    assert booking.lesson_id is not None
    assert _count(Student) == 1

def test_phone_formats_8_and_plus7_do_not_match(client, owner, student_factory, slot_factory, booking_factory):
    """`8 999…` и `+7 999…` не склеиваются: создаётся новый ученик.

    Это осознанное следствие примитивного сравнения (design.md D9, Risks):
    неверное склеивание двух разных людей хуже лишнего дубля, который
    педагог удалит сам.
    """
    from app.booking.models.booking import Booking
    from app.student.models.student import Student

    existing_id = student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", phone="+7 999 000-00-00"
    )
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id, name="Мария Петрова", contact="8 999 000-00-00")

    client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )

    booking = _get(Booking, booking_id)
    assert booking.status == "confirmed"
    assert booking.student_id != existing_id
    assert _count(Student) == 2


def test_confirm_creates_student_when_no_match(client, owner, slot_factory, booking_factory):
    """Без совпадения подтверждение создаёт ученика с признаком из формы."""
    from app.booking.models.booking import Booking
    from app.lesson.models.lesson import Lesson
    from app.student.models.student import Student

    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id, name="Новый Ученик", contact="+7 999 222-22-22")

    response = client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "adult"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    booking = _get(Booking, booking_id)
    assert booking.status == "confirmed"

    student = _get(Student, booking.student_id)
    assert student.first_name == "Новый"
    assert student.last_name == "Ученик"
    assert student.kind == "adult"
    assert student.phone == "+7 999 222-22-22"

    lesson = _get(Lesson, booking.lesson_id)
    assert lesson.student_id == student.id
    assert lesson.type == "individual"
    assert lesson.status == "planned"
    assert lesson.starts_at.replace(tzinfo=UTC) == FUTURE
    assert lesson.duration_min == 40

def test_confirm_requires_kind_for_new_student(client, owner, slot_factory, booking_factory):
    """Без признака «ребёнок/взрослый» ученик не создаётся, бронь ждёт."""
    from app.booking.models.booking import Booking
    from app.student.models.student import Student

    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id, name="Без Признака", contact="+7 999 333-33-33")

    response = client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "ребёнок или взрослый" in response.text
    assert _get(Booking, booking_id).status == "pending"
    assert _count(Student) == 0

def test_confirm_requires_choice_when_several_match(client, owner, student_factory, slot_factory, booking_factory):
    """Два совпадения — автоматически не выбирается ни один."""
    from app.booking.models.booking import Booking

    student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", phone="+7 999 000-00-00"
    )
    student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", phone="+7 999 000-00-00"
    )
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)

    response = client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )

    assert "выберите нужного" in response.text
    assert _get(Booking, booking_id).status == "pending"

def test_confirm_with_chosen_student_uses_it(client, owner, student_factory, slot_factory, booking_factory):
    """Явный выбор педагога при нескольких совпадениях подтверждает бронь."""
    from app.booking.models.booking import Booking

    student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", phone="+7 999 000-00-00"
    )
    chosen_id = student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", phone="+7 999 000-00-00"
    )
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)

    response = client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"student_id": chosen_id},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    booking = _get(Booking, booking_id)
    assert booking.status == "confirmed"
    assert booking.student_id == chosen_id

def test_confirm_rejects_when_time_taken_by_lesson(client, owner, student_factory, slot_factory, booking_factory):
    """Урок на времени окна отклоняет подтверждение (design D9, шаг 3)."""
    from app.booking.models.booking import Booking
    from app.lesson.models.lesson import Lesson

    student_id = student_factory(tutor_id=owner)
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)
    with SessionLocal() as session:
        session.add(
            Lesson(
                student_id=student_id,
                type="individual",
                starts_at=datetime(2027, 10, 14, 14, 20, tzinfo=UTC),
                duration_min=40,
                status="planned",
            )
        )
        session.commit()

    response = client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )

    assert "уже занято уроком" in response.text
    assert _get(Booking, booking_id).status == "pending"
    assert _count(Lesson) == 1

def test_confirm_does_not_use_archived_student(client, owner, student_factory, slot_factory, booking_factory):
    """Архивный ученик не подставляется: создаётся новый."""
    from app.booking.models.booking import Booking
    from app.student.models.student import Student

    archived_id = student_factory(
        tutor_id=owner,
        first_name="Мария",
        last_name="Петрова",
        phone="+7 999 000-00-00",
        status="archived",
    )
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)

    client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )

    booking = _get(Booking, booking_id)
    assert booking.status == "confirmed"
    assert booking.student_id != archived_id
    assert _count(Student) == 2

# --------------------------------------------------------------------------
# 5.3 Отклонение и отмена
# --------------------------------------------------------------------------

def test_reject_frees_slot_and_creates_nothing(client, owner, slot_factory, booking_factory):
    """Отклонение освобождает окно: ученик и урок не созданы."""
    from app.booking.models.booking import Booking
    from app.lesson.models.lesson import Lesson
    from app.slot.services.busy import SLOT_FREE, slot_states
    from app.student.models.student import Student

    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)

    response = client.post(
        f"/tutor/bookings/{booking_id}/reject",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "slot-saved"
    assert _get(Booking, booking_id).status == "rejected"
    assert _count(Student) == 0
    assert _count(Lesson) == 0

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        state = slot_states(session, owner, [slot], datetime.now(UTC))[slot_id]
    assert state == SLOT_FREE

def test_cancel_keeps_lesson_and_student(client, owner, slot_factory, booking_factory):
    """Отмена подтверждённой брони не удаляет урок; окно — «Занято уроком»."""
    from app.booking.models.booking import Booking
    from app.lesson.models.lesson import Lesson
    from app.slot.services.busy import SLOT_LESSON, slot_states
    from app.student.models.student import Student

    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)
    client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )
    confirmed = _get(Booking, booking_id)
    lesson_id = confirmed.lesson_id
    student_id = confirmed.student_id

    response = client.post(
        f"/tutor/bookings/{booking_id}/cancel",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers["HX-Trigger"] == "slot-saved"
    assert _get(Booking, booking_id).status == "cancelled"
    assert _get(Lesson, lesson_id) is not None
    assert _get(Student, student_id) is not None

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        state = slot_states(session, owner, [slot], datetime.now(UTC))[slot_id]
    assert state == SLOT_LESSON

def test_booking_actions_tell_htmx_not_to_swap(client, owner, slot_factory, booking_factory):
    """Подтверждение, отклонение и отмена закрывают диалог без подмены.

    Тот же `HX-Reswap: none`, что у действий окна: событие `slot-saved`
    приходит до подмены, диалог к этому моменту уже закрыт и отсоединён —
    подмена пустым телом давала `htmx:swapError` (найдено в браузере).
    """
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)

    rejected = client.post(
        f"/tutor/bookings/{booking_id}/reject",
        headers={"HX-Request": "true"},
    )
    assert rejected.headers["HX-Reswap"] == "none"

    second_id = booking_factory(slot_id)
    confirmed = client.post(
        f"/tutor/bookings/{second_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )
    assert confirmed.headers["HX-Reswap"] == "none"

    cancelled = client.post(
        f"/tutor/bookings/{second_id}/cancel",
        headers={"HX-Request": "true"},
    )
    assert cancelled.headers["HX-Reswap"] == "none"

    for response in (rejected, confirmed, cancelled):
        assert response.status_code == 200
        assert response.text == ""
        assert response.headers["HX-Trigger"] == "slot-saved"

def test_slot_becomes_free_after_lesson_deleted(client, owner, slot_factory, booking_factory):
    """Удаление урока после отмены возвращает окно в свободные."""
    from app.booking.models.booking import Booking
    from app.lesson.models.lesson import Lesson
    from app.slot.services.busy import SLOT_FREE, slot_states

    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)
    client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )
    client.post(f"/tutor/bookings/{booking_id}/cancel", headers={"HX-Request": "true"})
    lesson_id = _get(Booking, booking_id).lesson_id

    with SessionLocal() as session:
        session.delete(session.get(Lesson, lesson_id))
        session.commit()

    with SessionLocal() as session:
        slot = session.get(Slot, slot_id)
        state = slot_states(session, owner, [slot], datetime.now(UTC))[slot_id]
    assert state == SLOT_FREE

# --------------------------------------------------------------------------
# 5.4 Вьюхи: сессия, изоляция, завершающие статусы
# --------------------------------------------------------------------------

def test_confirm_requires_session(client):
    """Без сессии подтверждение перенаправляет на вход."""
    response = client.post("/tutor/bookings/any/confirm", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"

def test_foreign_booking_is_404(client, owner, tutor_factory, slot_factory, booking_factory):
    """Бронь окна чужого репетитора отвечает как несуществующая."""
    other_id = tutor_factory(email="booking-other@example.com")
    foreign_slot = slot_factory(other_id)
    foreign_booking = booking_factory(foreign_slot)

    for action in ("confirm", "reject", "cancel"):
        response = client.post(
            f"/tutor/bookings/{foreign_booking}/{action}",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 404, action

def test_repeat_action_on_final_booking_is_rejected(client, owner, slot_factory, booking_factory):
    """Повторное действие на завершающей брони отклоняется."""
    from app.booking.models.booking import Booking

    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)
    client.post(f"/tutor/bookings/{booking_id}/reject", headers={"HX-Request": "true"})

    response = client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )

    assert "уже завершена" in response.text
    assert _get(Booking, booking_id).status == "rejected"

def test_reject_confirmed_booking_is_rejected(client, owner, slot_factory, booking_factory):
    """Подтверждённую бронь нельзя отклонить — только отменить."""
    from app.booking.models.booking import Booking

    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)
    client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )

    response = client.post(
        f"/tutor/bookings/{booking_id}/reject",
        headers={"HX-Request": "true"},
    )

    assert "отмените её" in response.text
    assert _get(Booking, booking_id).status == "confirmed"

def test_confirm_without_js_redirects_to_calendar(client, owner, slot_factory, booking_factory):
    """Без `HX-Request` подтверждение отвечает 303 на календарь."""
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)

    response = client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/calendar"

# --------------------------------------------------------------------------
# Диалог окна: блок брони и действия
# --------------------------------------------------------------------------

def test_dialog_shows_pending_booking_actions(client, owner, slot_factory, booking_factory):
    """У ожидающей брони видны имя, контакт и действия подтверждения."""
    slot_id = slot_factory(owner)
    booking_factory(slot_id, name="Мария Петрова", contact="+7 999 000-00-00")

    response = client.get(f"/tutor/slots/{slot_id}")

    assert response.status_code == 200
    assert "Заявка на это окно" in response.text
    assert "Мария Петрова" in response.text
    assert "+7 999 000-00-00" in response.text
    assert "Подтвердить" in response.text
    assert "Отклонить" in response.text
    assert "Отменить бронь" not in response.text
    # Окно с активной бронью не удаляется.
    assert "Точно удалить?" not in response.text

def test_dialog_shows_cancel_for_confirmed_booking(client, owner, slot_factory, booking_factory):
    """У подтверждённой брони доступна отмена, подтверждения уже нет."""
    slot_id = slot_factory(owner)
    booking_id = booking_factory(slot_id)
    client.post(
        f"/tutor/bookings/{booking_id}/confirm",
        data={"kind": "child"},
        headers={"HX-Request": "true"},
    )

    response = client.get(f"/tutor/slots/{slot_id}")

    assert "Отменить бронь" in response.text
    assert "Подтвердить" not in response.text
    assert "Занято записью" in response.text

def test_booking_forms_are_not_nested_in_slot_form(client, owner, slot_factory, booking_factory):
    """Формы брони — соседи формы окна, а не её потомки.

    Найдено в браузере: вложенные `<form>` HTML запрещает — браузер
    выбрасывает внутренний тег, и кнопка «Подтвердить» отправляла внешнюю
    форму окна (POST на `/tutor/slots/<id>` вместо
    `/tutor/bookings/<id>/confirm`), поэтому заявка оставалась ожидающей.
    Проверяется разметка, а не дерево DOM: `html.parser` разбирает теги так
    же, как браузер, и видит вложенность, которую браузер бы выбросил.
    """
    from html.parser import HTMLParser

    slot_id = slot_factory(owner)
    booking_factory(slot_id)

    text = client.get(f"/tutor/slots/{slot_id}").text

    class _Forms(HTMLParser):
        """Глубина вложенности `<form>` в момент открытия каждой формы."""

        def __init__(self):
            super().__init__()
            self.depth = 0
            self.nested = []

        def handle_starttag(self, tag, attrs):
            if tag != "form":
                return
            attributes = dict(attrs)
            if self.depth:
                self.nested.append(attributes)
            self.depth += 1

        def handle_endtag(self, tag):
            if tag == "form" and self.depth:
                self.depth -= 1

    parser = _Forms()
    parser.feed(text)

    assert parser.nested == [], (
        "Формы брони вложены в форму окна: браузер выбросит вложенный <form>, "
        "и кнопки действий отправят форму окна"
    )
    # Обе формы на месте и каждая ведёт на свой адрес.
    assert 'hx-post="/tutor/bookings/' in text
    assert f'hx-post="/tutor/slots/{slot_id}"' in text
    # «Сохранить» стоит в футере, вне формы, и связана с ней атрибутом `form`.
    assert 'type="submit" form="slot-form"' in text
    assert 'id="slot-form"' in text

def test_dialog_offers_student_choice_for_several_matches(client, owner, student_factory, slot_factory, booking_factory):
    """При двух совпадениях диалог показывает селект выбора ученика."""
    student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", phone="+7 999 000-00-00"
    )
    student_factory(
        tutor_id=owner, first_name="Мария", last_name="Петрова", phone="+7 999 000-00-00"
    )
    slot_id = slot_factory(owner)
    booking_factory(slot_id)

    response = client.get(f"/tutor/slots/{slot_id}")

    assert 'name="student_id"' in response.text
    assert "выберите нужного" in response.text
