"""Тесты публичной страницы записи: ссылка, сетка, выбор окна, заявка, лимит.

Проверяется поведение через HTTP без сессии — тем же путём, что у ученика
(правило AGENTS.md). Страница не должна раскрывать данные других учеников,
поэтому часть тестов ищет в разметке отсутствие подстрок.

Сетка показывает публичные окна недели: свободное — ссылкой выбора,
занятое — карточкой «Занято» без указания, кем занято (спека public-booking,
design D1). Приватные и прошедшие окна не показываются вовсе.
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

def _select_url(tutor_id: str, slot_id: str, monday: date = MONDAY) -> str:
    """Адрес страницы с выбранным окном (ссылка свободной карточки)."""
    return f"{_public_url(tutor_id, monday)}&slot={slot_id}"

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
    assert "Запись на пробный урок" in response.text
    assert "Преподаватель:" in response.text

# --------------------------------------------------------------------------
# 6.2 Сетка недели
# --------------------------------------------------------------------------

def test_grid_shows_free_and_busy_slots(client, tutor_factory, slot_factory):
    """Свободное окно — ссылка выбора, занятое — карточка «Занято»."""
    from app.booking.models.booking import Booking
    from app.lesson.models.lesson import Lesson

    tutor_id = tutor_factory(email="public-grid@example.com")
    free_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    busy_lesson_id = slot_factory(tutor_id, datetime(2027, 10, 12, 13, 0, tzinfo=UTC))
    busy_booking_id = slot_factory(tutor_id, datetime(2027, 10, 12, 14, 0, tzinfo=UTC))

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
    # Свободное окно: время видно, карточка — ссылка на выбор.
    assert "10:00" in response.text
    assert f"slot={free_id}" in response.text
    assert "Свободно" in response.text
    # Занятые окна видны, но безлики: время есть, выбора нет.
    assert "13:00" in response.text
    assert "14:00" in response.text
    assert "Занято" in response.text
    for busy_id in (busy_lesson_id, busy_booking_id):
        assert f"slot={busy_id}" not in response.text, busy_id
    # Имя ученика не попадает в разметку.
    assert "Иван" not in response.text

def test_page_hides_private_and_past_slots(client, tutor_factory, slot_factory):
    """Приватное и прошедшее окно не показываются ученику."""
    tutor_id = tutor_factory(email="public-filter@example.com")
    slot_factory(tutor_id, datetime(2027, 10, 12, 11, 0, tzinfo=UTC), is_public=False)
    slot_factory(tutor_id, datetime(2026, 1, 5, 10, 0, tzinfo=UTC))

    response = client.get(_public_url(tutor_id))

    assert response.status_code == 200
    assert "11:00" not in response.text
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
    # Пустой день объясняется подписью, а не пустотой.
    assert "нет мест" in response.text

def test_empty_week_shows_no_seats_per_day(client, tutor_factory):
    """Пустая неделя даёт сетку из семи дней с подписью «нет мест»."""
    tutor_id = tutor_factory(email="public-empty@example.com")

    response = client.get(_public_url(tutor_id))

    assert response.status_code == 200
    assert response.text.count("нет мест") == 7
    assert "Понедельник" in response.text
    assert "Воскресенье" in response.text

def test_week_fully_unavailable_shows_reason(
    client, tutor_factory, unavailability_factory
):
    """Неделя целиком в отпуске объясняет причину вместо сетки окон."""
    tutor_id = tutor_factory(email="public-full-vacation@example.com")
    unavailability_factory(
        tutor_id=tutor_id,
        start_date=MONDAY,
        end_date=date(2027, 10, 17),
    )

    response = client.get(_public_url(tutor_id))

    assert "Педагог недоступен: Отпуск" in response.text

def test_page_warns_about_timezone(client, tutor_factory):
    """Баннер о поясе показывает зону педагога и смещение UTC."""
    tutor_id = tutor_factory(
        email="public-zone@example.com", timezone="Europe/Samara"
    )

    response = client.get(_public_url(tutor_id))

    assert "Внимание: время указано по Europe/Samara (UTC+4)" in response.text
    assert "Учитывайте разницу с вашим часовым поясом" in response.text

def test_week_navigation_shows_range(client, tutor_factory):
    """Подпись недели — диапазон дат «11 окт. — 17 окт. 2027»."""
    tutor_id = tutor_factory(email="public-range@example.com")

    response = client.get(_public_url(tutor_id, MONDAY))

    assert "11 окт. — 17 окт. 2027" in response.text

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
    assert f"slot={own_slot}" in response.text
    assert f"slot={foreign_slot}" not in response.text
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
# 6.3 Выбор окна
# --------------------------------------------------------------------------

def test_selected_slot_opens_form(client, tutor_factory, slot_factory):
    """`?slot=` свободного окна подсвечивает его и открывает форму заявки."""
    tutor_id = tutor_factory(email="public-select@example.com", timezone="UTC")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    response = client.get(_select_url(tutor_id, slot_id))

    assert response.status_code == 200
    assert "Запись на урок" in response.text
    assert "Выбрано:" in response.text
    assert "12 октября, вторник, 10:00 — 10:40" in response.text
    assert f'value="{slot_id}"' in response.text
    assert "Ваше имя" in response.text

def test_no_form_without_selection(client, tutor_factory, slot_factory):
    """Без выбора формы нет — только сетка."""
    tutor_id = tutor_factory(email="public-noselect@example.com")
    slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    response = client.get(_public_url(tutor_id))

    assert "Запись на урок" not in response.text
    assert "Выбрано:" not in response.text

def test_unknown_slot_is_ignored(client, tutor_factory):
    """Несуществующий `slot` игнорируется: сетка без формы, без ошибки."""
    tutor_id = tutor_factory(email="public-badslot@example.com")

    response = client.get(_select_url(tutor_id, "00000000-0000-0000-0000-000000000000"))

    assert response.status_code == 200
    assert "Запись на урок" not in response.text

def test_busy_slot_cannot_be_selected(client, tutor_factory, slot_factory, booking_factory):
    """Занятое окно выбором не становится: форма не открывается."""
    tutor_id = tutor_factory(email="public-busyselect@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    booking_factory(slot_id)

    response = client.get(_select_url(tutor_id, slot_id))

    assert response.status_code == 200
    assert "Запись на урок" not in response.text

def test_foreign_slot_cannot_be_selected(client, tutor_factory, slot_factory):
    """Окно другого репетитора через `?slot=` не выбирается."""
    tutor_id = tutor_factory(email="public-foreignselect@example.com")
    other_id = tutor_factory(email="public-foreignowner@example.com")
    foreign_slot = slot_factory(other_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    response = client.get(_select_url(tutor_id, foreign_slot))

    assert response.status_code == 200
    assert "Запись на урок" not in response.text

# --------------------------------------------------------------------------
# 6.4 Форма заявки
# --------------------------------------------------------------------------

def test_booking_creates_pending_with_comment(client, tutor_factory, slot_factory):
    """Валидная заявка создаёт бронь «Ожидает подтверждения» с комментарием."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-book@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    response = client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": slot_id,
            "name": "Мария Петрова",
            "contact": "+7 999 000-00-00",
            "comment": "Хочу подтянуть разговорный английский",
            "start": MONDAY.isoformat(),
        },
    )

    assert response.status_code == 200
    # Экран успеха: заголовок, пояснение и выбранное время (design D3).
    assert "Заявка отправлена!" in response.text
    assert "Ожидайте подтверждение от преподавателя." in response.text
    assert "Выбранное время:" in response.text
    assert "12 октября 2027 10:00 — 10:40" in response.text

    with SessionLocal() as session:
        bookings = session.query(Booking).all()
    assert len(bookings) == 1
    assert bookings[0].status == "pending"
    assert bookings[0].name == "Мария Петрова"
    assert bookings[0].comment == "Хочу подтянуть разговорный английский"
    assert bookings[0].student_id is None
    assert bookings[0].lesson_id is None

def test_booking_without_comment_stores_none(client, tutor_factory, slot_factory):
    """Пустой комментарий сохраняется как NULL, а не пустой строкой."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-nocomment@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": slot_id,
            "name": "Мария",
            "contact": "+7 999 000-00-00",
            "comment": "   ",
        },
    )

    with SessionLocal() as session:
        assert session.query(Booking).one().comment is None

def test_too_long_comment_is_rejected(client, tutor_factory, slot_factory):
    """Комментарий длиннее 500 символов блокирует заявку."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-longcomment@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))

    response = client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": slot_id,
            "name": "Мария",
            "contact": "+7 999 000-00-00",
            "comment": "а" * 501,
        },
    )

    assert "Комментарий — не длиннее 500 символов." in response.text
    with SessionLocal() as session:
        assert session.query(Booking).count() == 0

@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "   "}, "Укажите имя."),
        ({"contact": ""}, "Укажите телефон или мессенджер для связи."),
    ],
    ids=["no-name", "no-contact"],
)
def test_booking_without_required_field_is_rejected(
    client, tutor_factory, slot_factory, overrides, message
):
    """Пустое имя или контакт блокируют заявку, бронь не создаётся."""
    from app.booking.models.booking import Booking

    tutor_id = tutor_factory(email="public-invalid@example.com")
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    data = {
        "slot_id": slot_id,
        "name": "Мария",
        "contact": "+7 999 000-00-00",
        "start": MONDAY.isoformat(),
    }
    data.update(overrides)

    response = client.post(f"/s/{tutor_id}/book", data=data)

    assert response.status_code == 200
    assert message in response.text
    # Введённые значения не теряются: выбранное окно и форма снова на месте.
    assert f'value="{slot_id}"' in response.text
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
# 6.5 Комментарий виден педагогу
# --------------------------------------------------------------------------

def test_tutor_sees_booking_comment_in_slot_dialog(
    client, tutor_factory, slot_factory
):
    """Комментарий заявки показывается педагогу в диалоге окна."""
    tutor_id = tutor_factory(
        email="public-dialog@example.com",
        password="Секретный-Пароль-1",
        timezone="UTC",
    )
    slot_id = slot_factory(tutor_id, datetime(2027, 10, 12, 10, 0, tzinfo=UTC))
    client.post(
        f"/s/{tutor_id}/book",
        data={
            "slot_id": slot_id,
            "name": "Мария Петрова",
            "contact": "+7 999 000-00-00",
            "comment": "Английский для работы",
        },
    )
    client.post(
        "/tutor/login",
        data={
            "email": "public-dialog@example.com",
            "password": "Секретный-Пароль-1",
        },
        follow_redirects=False,
    )

    response = client.get(f"/tutor/slots/{slot_id}")

    assert response.status_code == 200
    assert "Английский для работы" in response.text

# --------------------------------------------------------------------------
# 6.6 Ограничение частоты
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
    assert "Заявка отправлена!" in first.text

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

    assert "Заявка отправлена!" in response.text

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

    assert "Заявка отправлена!" in ok.text

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
