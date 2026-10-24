"""Тесты публичной страницы записи: ссылка, окна, заявка, лимит.

Проверяется поведение через HTTP без сессии — тем же путём, что у ученика
(правило AGENTS.md). Страница не должна раскрывать данные других учеников,
поэтому часть тестов ищет в разметке отсутствие подстрок.
"""

from datetime import UTC, date, datetime

import pytest

from app.database import SessionLocal

# Понедельник 11.10.2027 — будущая неделя: «сегодня» в проекте 23.10.2026,
# иначе окна получили бы состояние `past` и не показались бы вовсе.
MONDAY = date(2027, 10, 11)

def _public_url(tutor_id: str, monday: date = MONDAY) -> str:
    """Адрес публичной страницы недели."""
    return f"/s/{tutor_id}?start={monday.isoformat()}"

# --------------------------------------------------------------------------
# 6.1 Ссылка: сборка и разбор
# --------------------------------------------------------------------------

def test_public_url_contains_tutor_and_monday():
    """Ссылка несёт `tutor_id` и понедельник недели."""
    from app.slot.services.public_link import public_url

    url = public_url("tutor-1", date(2027, 10, 14))

    assert url == "/s/tutor-1?start=2027-10-11"

def test_public_url_normalizes_any_day_of_week():
    """Любая дата недели нормализуется к понедельнику."""
    from app.slot.services.public_link import public_url

    for day in (date(2027, 10, 11), date(2027, 10, 14), date(2027, 10, 17)):
        assert public_url("t", day) == "/s/t?start=2027-10-11"

def test_week_from_start_falls_back_to_current_week():
    """Кривой или пустой `?start=` даёт текущую неделю, а не 500."""
    from app.slot.services.public_link import week_from_start

    today = date(2027, 10, 14)
    assert week_from_start(None, today) == date(2027, 10, 11)
    assert week_from_start("не дата", today) == date(2027, 10, 11)
    assert week_from_start("2027-10-20", today) == date(2027, 10, 18)

def test_unknown_tutor_is_404(client):
    """Неизвестный `tutor_id` даёт страницу «не найдено»."""
    response = client.get("/s/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404

def test_public_page_opens_without_session(client, tutor_factory):
    """Публичная страница открывается без входа и не перенаправляет на логин."""
    tutor_id = tutor_factory(email="public-anon@example.com")

    response = client.get(_public_url(tutor_id))

    assert response.status_code == 200
    assert "Запись на занятие" in response.text

# --------------------------------------------------------------------------
# 6.2 Что показывается на странице
# --------------------------------------------------------------------------

def test_page_shows_only_free_public_future_slots(client, tutor_factory, slot_factory):
    """Приватное, прошедшее и занятое окно не показываются."""
    from app.booking.models.booking import Booking
    from app.lesson.models.lesson import Lesson

    tutor_id = tutor_factory(email="public-filter@example.com")
    free_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    private_id = slot_factory(tutor_id, datetime(2027, 10, 12, 11, 0, tzinfo=UTC), is_public=False)
    busy_lesson_id = slot_factory(tutor_id, datetime(2027, 10, 12, 13, 0, tzinfo=UTC))
    busy_booking_id = slot_factory(tutor_id, datetime(2027, 10, 12, 14, 0, tzinfo=UTC))
    past_id = slot_factory(tutor_id, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    # Окно 13:00 занято уроком, 14:00 — активной бронью.
    with SessionLocal() as session:
        from app.student.models.student import Student

        student = Student(tutor_id=tutor_id, first_name="Иван", kind="child")
        session.add(student)
        session.flush()
        session.add(
            Lesson(
                student_id=student.id,
                type="individual",
                starts_at=datetime(2027, 10, 12, 13, 0, tzinfo=UTC),
                duration_min=40,
                status="planned",
            )
        )
        session.add(
            Booking(
                slot_id=busy_booking_id,
                name="Заявитель",
                contact="+7 999 000-00-00",
            )
        )
        session.commit()

    response = client.get(_public_url(tutor_id))

    assert response.status_code == 200
    assert "10:00" in response.text
    assert f'value="{free_id}"' in response.text
    # Приватное, занятое уроком, занятое бронью и прошедшее окна отсутствуют.
    for hidden in (private_id, busy_lesson_id, busy_booking_id, past_id):
        assert f'value="{hidden}"' not in response.text, hidden
    assert "11:00" not in response.text
    assert "13:00" not in response.text
    assert "14:00" not in response.text
    assert "05.01.2026" not in response.text

def test_page_hides_slot_in_unavailable_day(client, tutor_factory, unavailability_factory, slot_factory):
    """Окно в отмеченный день не показывается ученику."""
    tutor_id = tutor_factory(email="public-vacation@example.com")
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=MONDAY,
        end_date=MONDAY,
    )
    slot_factory(tutor_id, datetime(2027, 10, 11, 10, 0, tzinfo=UTC))

    response = client.get(_public_url(tutor_id))

    assert response.status_code == 200
    assert "10:00" not in response.text
    assert "свободных окон нет" in response.text

def test_empty_week_explains_no_slots(client, tutor_factory):
    """Пустая неделя даёт пояснение, а не ошибку."""
    tutor_id = tutor_factory(email="public-empty@example.com")

    response = client.get(_public_url(tutor_id))

    assert response.status_code == 200
    assert "свободных окон нет" in response.text

def test_week_fully_unavailable_shows_reason(
    client, tutor_factory, unavailability_factory
):
    """Неделя целиком в отпуске объясняет причину вместо списка окон."""
    tutor_id = tutor_factory(email="public-full-vacation@example.com")
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=MONDAY,
        end_date=date(2027, 10, 17),
    )

    response = client.get(_public_url(tutor_id))

    assert "Педагог недоступен: Отпуск" in response.text

def test_page_warns_about_timezone(client, tutor_factory):
    """Подпись о поясе показывает зону педагога."""
    tutor_id = tutor_factory(
        email="public-zone@example.com", timezone="Europe/Samara"
    )

    response = client.get(_public_url(tutor_id))

    assert "Обратите внимание, время указано: Europe/Samara" in response.text

def test_page_shows_only_own_tutor_slots(client, tutor_factory, slot_factory):
    """Публичная страница не показывает окна другого репетитора.

    Изоляция по репетитору на единственной поверхности без сессии:
    `tutor_id` берётся из адреса, и выборка окон идёт по нему. Чужое окно
    не попадает в разметку и не бронируется через эту ссылку (последнее —
    `test_booking_on_foreign_slot_is_rejected`).
    """
    own_id = tutor_factory(email="public-own@example.com")
    other_id = tutor_factory(email="public-other@example.com")
    own_slot = slot_factory(own_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    foreign_slot = slot_factory(other_id, datetime(2027, 10, 12, 11, 0, tzinfo=UTC))

    response = client.get(_public_url(own_id))

    assert response.status_code == 200
    assert f'value="{own_slot}"' in response.text
    assert f'value="{foreign_slot}"' not in response.text
    assert "11:00" not in response.text

def test_page_does_not_leak_student_data(client, tutor_factory, student_factory, slot_factory):
    """В разметке нет имён учеников, заметок и контактов."""
    from app.lesson.models.lesson import Lesson

    tutor_id = tutor_factory(email="public-leak@example.com")
    student_id = student_factory(
        tutor_id=tutor_id,
        first_name="Секретноеимя",
        last_name="Секретнаяфамилия",
        phone="+7 999 123-45-67",
        notes="Секретнаязаметка",
    )
    with SessionLocal() as session:
        session.add(
            Lesson(
                student_id=student_id,
                type="individual",
                starts_at=datetime(2027, 10, 12, 15, 0, tzinfo=UTC),
                duration_min=40,
                status="planned",
                note="Секретнаязаметкаурока",
            )
        )
        session.commit()
    slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    response = client.get(_public_url(tutor_id))

    assert response.status_code == 200
    for secret in (
        "Секретноеимя",
        "Секретнаяфамилия",
        "999 123-45-67",
        "Секретнаязаметка",
        "Секретнаязаметкаурока",
    ):
        assert secret not in response.text, secret

# --------------------------------------------------------------------------
# 6.3 Форма заявки
# --------------------------------------------------------------------------

def test_booking_creates_pending(client, tutor_factory, slot_factory):
    """Валидная заявка создаёт бронь в статусе «Ожидает подтверждения»."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-book@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    response = client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": slot_id,
            "name": "Мария Петрова",
            "contact": "+7 999 000-00-00",
            "start": MONDAY.isoformat(),
        },
    )

    assert response.status_code == 200
    assert "Заявка отправлена" in response.text

    with SessionLocal() as session:
        bookings = session.query(Booking).all()
    assert len(bookings) == 1
    assert bookings[0].status == "pending"
    assert bookings[0].name == "Мария Петрова"
    assert bookings[0].student_id is None
    assert bookings[0].lesson_id is None

@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "   "}, "Укажите имя."),
        ({"contact": ""}, "Укажите телефон или мессенджер для связи."),
    ],
    ids=["no-name", "no-contact"],
)
def test_booking_without_required_field_is_rejected(
    client, tutor_factory, overrides, message
, slot_factory):
    """Пустое имя или контакт блокируют заявку, бронь не создаётся."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-invalid@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    data = {"slot_id": slot_id, "name": "Мария", "contact": "+7 999 000-00-00"}
    data.update(overrides)

    response = client.post(f"/s/{tutor_id}/book", data=data)

    assert response.status_code == 200
    assert message in response.text
    with SessionLocal() as session:
        assert session.query(Booking).count() == 0

def test_booking_on_taken_slot_is_rejected(client, tutor_factory, slot_factory):
    """Окно, ставшее занятым, заявку не принимает."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-taken@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    with SessionLocal() as session:
        session.add(
            Booking(slot_id=slot_id, name="Первый", contact="+7 999 111-11-11")
        )
        session.commit()

    response = client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": slot_id,
            "name": "Второй",
            "contact": "+7 999 222-22-22",
        },
    )

    assert "уже занято" in response.text
    with SessionLocal() as session:
        assert session.query(Booking).count() == 1

def test_booking_on_private_slot_is_rejected(client, tutor_factory, slot_factory):
    """Окно, с которого сняли публичность, заявку не принимает."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-private@example.com")
    slot_id = slot_factory(
        tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC), is_public=False
    )

    response = client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": slot_id,
            "name": "Мария",
            "contact": "+7 999 000-00-00",
        },
    )

    assert "недоступно для записи" in response.text
    with SessionLocal() as session:
        assert session.query(Booking).count() == 0

def test_booking_on_foreign_slot_is_rejected(client, tutor_factory, slot_factory):
    """Окно другого репетитора через ссылку не бронируется."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-owner@example.com")
    other_id = tutor_factory(email="public-foreign@example.com")
    foreign_slot = slot_factory(other_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    response = client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": foreign_slot,
            "name": "Мария",
            "contact": "+7 999 000-00-00",
        },
    )

    assert "больше недоступно" in response.text
    with SessionLocal() as session:
        assert session.query(Booking).count() == 0

# --------------------------------------------------------------------------
# 6.4 Ограничение частоты
# --------------------------------------------------------------------------

def test_rate_limit_blocks_sixth_attempt(client, tutor_factory, slot_factory):
    """Шестая заявка подряд с одного клиента отклоняется (design D12).

    Счётчик считает **отправки**, а не созданные брони: окно принимает
    только одну активную бронь, поэтому «считать успешные» сделало бы
    лимит недостижимым. Проверяется реальный путь ученика — шесть POST
    подряд с одного клиента.
    """
    from app.booking.models.booking import Booking
    from app.booking.models.booking_attempt import BOOKING_ATTEMPT_LIMIT

    tutor_id = tutor_factory(email="public-limit@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    data = {
        "slot_id": slot_id,
        "name": "Мария",
        "contact": "+7 999 000-00-00",
        "start": MONDAY.isoformat(),
    }

    # Первая заявка проходит и создаёт бронь.
    first = client.post(f"/s/{tutor_id}/book", data=data)
    assert "Заявка отправлена" in first.text

    # Остальные до лимита отклоняются как «время занято», но считаются.
    for _ in range(BOOKING_ATTEMPT_LIMIT - 1):
        response = client.post(f"/s/{tutor_id}/book", data=data)
        assert "уже занято" in response.text

    # Шестая отправка упирается в лимит.
    limited = client.post(f"/s/{tutor_id}/book", data=data)
    assert "Слишком много заявок подряд" in limited.text

    with SessionLocal() as session:
        # Бронь по-прежнему одна: лимит не создаёт строк.
        assert session.query(Booking).count() == 1

def test_rate_limit_is_per_slot(client, tutor_factory, slot_factory):
    """Лимит считается на окно: другое окно принимает заявку."""
    from app.booking.models.booking_attempt import BOOKING_ATTEMPT_LIMIT

    tutor_id = tutor_factory(email="public-limit-slot@example.com")
    first_slot = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    second_slot = slot_factory(tutor_id, datetime(2027, 10, 12, 12, 0, tzinfo=UTC))

    for _ in range(BOOKING_ATTEMPT_LIMIT + 1):
        client.post(
            f"/s/{tutor_id}/book",
            data={
                "slot_id": first_slot,
                "name": "Мария",
                "contact": "+7 999 000-00-00",
            },
        )

    # По первому окну лимит исчерпан, по второму — нет.
    response = client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": second_slot,
            "name": "Мария",
            "contact": "+7 999 000-00-00",
        },
    )

    assert "Заявка отправлена" in response.text

def test_rate_limit_does_not_eat_limit_on_form_errors(client, tutor_factory, slot_factory):
    """Опечатка в имени не съедает лимит: форма проверяется до счётчика."""
    from app.booking.models.booking_attempt import BOOKING_ATTEMPT_LIMIT

    tutor_id = tutor_factory(email="public-limit-typo@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    for _ in range(BOOKING_ATTEMPT_LIMIT + 1):
        response = client.post(
            f"/s/{tutor_id}/book",
            data={"slot_id": slot_id, "name": "  ", "contact": "+7 999 000-00-00"},
        )
        assert "Укажите имя." in response.text

    # После серии опечаток настоящая заявка проходит.
    ok = client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": slot_id,
            "name": "Мария",
            "contact": "+7 999 000-00-00",
        },
    )

    assert "Заявка отправлена" in ok.text

def test_rate_limit_purges_old_rows():
    """Счётчики старше срока хранения удаляются при обращении."""
    from datetime import timedelta

    from app.booking.models.booking_attempt import (
        BOOKING_ATTEMPT_RETENTION_HOURS,
        BookingAttempt,
    )
    from app.booking.services.rate_limit import is_rate_limited
    from app.common.services.tutor_time import now_utc

    now = now_utc()
    with SessionLocal() as session:
        session.add(
            BookingAttempt(
                key="deadbeef",
                window_start=now - timedelta(hours=BOOKING_ATTEMPT_RETENTION_HOURS + 1),
                count=5,
            )
        )
        session.commit()

        is_rate_limited(session, "slot", "client", now=now)

    with SessionLocal() as session:
        assert session.query(BookingAttempt).filter_by(key="deadbeef").count() == 0

def test_rate_limit_key_does_not_store_slot_or_client():
    """Ключ счётчика — хеш: ни окна, ни адреса клиента в открытом виде."""
    from app.booking.services.rate_limit import attempt_key

    key = attempt_key("slot-123", "10.0.0.1|Mozilla")

    assert len(key) == 64
    assert "slot-123" not in key
    assert "10.0.0.1" not in key
