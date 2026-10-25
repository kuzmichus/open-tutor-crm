"""Тесты главной страницы репетитора (`/tutor/`): дашборд «сегодня».

Даты в тестах строятся от «сейчас» в зоне репетитора (фабрика по умолчанию
даёт UTC), а не от фиксированных: карточки живут сегодняшним днём и
текущим месяцем, и тест, прибитый к октябрю 2026, сломался бы в ноябре.
"""

import re
from datetime import UTC, datetime, timedelta

from app.common.services.tutor_time import local_day_bounds, today_local
from app.database import SessionLocal
from app.tutor.models.tutor import Tutor
from app.tutor.models.tutor_session import TutorSession
from app.tutor.services.clock import utcnow
from app.tutor.services.sessions import COOKIE_NAME

PASSWORD = "Секретный-Пароль-1"

# Независимые копии подписей месяцев: проверяем, что на странице месяц
# именно текущий, не доверяя тому же модулю, что и шаблону.
_SHORT_MONTHS = (
    "янв.", "февр.", "мар.", "апр.", "мая", "июн.",
    "июл.", "авг.", "сент.", "окт.", "нояб.", "дек.",
)
_MONTHS = (
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
)


def _login(client, tutor_factory, email="dash-user@example.com", name="Дашбордный", **extra):
    """Репетитор с заводской карточкой (зона UTC) и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD, **extra)
    client.post("/tutor/login", data={"email": email, "password": PASSWORD})
    return tutor_id


def _tutor(tutor_id):
    with SessionLocal() as db:
        return db.get(Tutor, tutor_id)


def _stat_value(html: str, label: str) -> str:
    """Значение стат-карточки по её подписи (блок: подпись → число)."""
    match = re.search(
        rf'{label}</span>.*?stat-card__value">([^<]+)</div>', html, flags=re.S
    )
    assert match, f"нет стат-карточки «{label}»"
    return match.group(1).strip()


def _month_noon(tutor) -> datetime:
    """Полдень 1-го числа текущего месяца педагога (зона тестов — UTC)."""
    first = today_local(tutor).replace(day=1)
    return datetime(first.year, first.month, first.day, 12, tzinfo=UTC)


def test_redirect_to_login_without_session(client):
    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_forged_token_redirects(client):
    """Подделанный/неизвестный токен в cookie приводит к редиректу на вход."""
    client.cookies.set(COOKIE_NAME, "forged-token-not-in-db")
    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_expired_session_redirects(client, tutor_factory):
    """Истёкшая сессия не открывает главную."""
    tutor_id = tutor_factory(email="exp@example.com", password=PASSWORD)
    client.post("/tutor/login", data={"email": "exp@example.com", "password": PASSWORD})
    with SessionLocal() as db:
        for row in db.query(TutorSession).filter_by(tutor_id=tutor_id).all():
            row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_session_of_deleted_tutor_redirects(client, tutor_factory):
    """Сессия удалённого репетитора не открывает главную.

    С включённой `PRAGMA foreign_keys=ON` сессия не может ссылаться на
    несуществующего репетитора, поэтому при удалении репетитора сначала
    удаляются его сессии — ровно так, как это сделает будущий сценарий
    удаления аккаунта.
    """
    from sqlalchemy import delete

    tutor_id = tutor_factory(email="gone@example.com", password=PASSWORD)
    client.post("/tutor/login", data={"email": "gone@example.com", "password": PASSWORD})
    with SessionLocal() as db:
        db.execute(delete(TutorSession).where(TutorSession.tutor_id == tutor_id))
        db.delete(db.get(Tutor, tutor_id))
        db.commit()

    response = client.get("/tutor/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"


def test_dashboard_stat_cards(
    client,
    tutor_factory,
    student_factory,
    lesson_factory,
    operation_factory,
):
    """Четыре карточки считают только свои данные за свой период."""
    tutor_id = _login(client, tutor_factory, email="stats@example.com")
    tutor = _tutor(tutor_id)

    day_start, _ = local_day_bounds(today_local(tutor), tutor)
    month_start = _month_noon(tutor)
    old = datetime(2020, 1, 15, 12, 0, tzinfo=UTC)

    # Ученики: 3 активных, плюс архив и новый — карточка их не считает.
    for status in ("active", "active", "active", "archived", "new"):
        student_factory(tutor_id=tutor_id, status=status)
    # Уроки вешаем на ученика тестового репетитора: factory со
    # student_id=None завёл бы ученика чужого (нового) репетитора.
    student = student_factory(tutor_id=tutor_id, status="new")

    # Уроки сегодня: два запланированных — счётчик «Запланировано» = 2
    # (длительность у карточки «часов» не учитывается, статус не «completed»).
    lesson_factory(student_id=student, status="planned", starts_at=day_start + timedelta(hours=10))
    lesson_factory(
        student_id=student,
        status="planned",
        starts_at=day_start + timedelta(hours=13),
        duration_min=120,
    )
    # Проведённый 90 минут в текущем месяце: 2 часа в карточке.
    lesson_factory(student_id=student, status="completed", starts_at=month_start, duration_min=90)
    # Проведённый вне месяца (2020) не считается.
    lesson_factory(student_id=student, status="completed", starts_at=old, duration_min=180)

    # Платежи: в доход месяца — только оплаченный 2000 в этом месяце.
    operation_factory(student_id=student, amount=2000, status="paid", occurred_at=month_start)
    operation_factory(student_id=student, amount=5000, status="pending", occurred_at=month_start)
    operation_factory(student_id=student, amount=10000, status="paid", occurred_at=old)

    response = client.get("/tutor/")
    assert response.status_code == 200

    assert _stat_value(response.text, "Уроки сегодня") == "2"
    assert _stat_value(response.text, "Активные ученики") == "3"
    assert _stat_value(response.text, "Доход за месяц") == "2\u00a0000\u00a0₽"
    assert _stat_value(response.text, "Проведено часов") == "2"

    assert "Запланировано" in response.text
    assert "Всего активных" in response.text
    assert f"За {_MONTHS[today_local(tutor).month - 1]}" in response.text
    assert "За текущий месяц" in response.text


def test_dashboard_schedule_lists_today_lessons(
    client,
    tutor_factory,
    student_factory,
    lesson_factory,
):
    """Расписание показывает уроки сегодня: имя, предмет и интервал."""
    tutor_id = _login(
        client, tutor_factory, email="schedule@example.com", subject="Английский язык"
    )
    tutor = _tutor(tutor_id)
    day_start, _ = local_day_bounds(today_local(tutor), tutor)

    ivan = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Иванов")
    anna = student_factory(tutor_id=tutor_id, first_name="Анна", last_name="Смирнова")
    lesson_factory(
        student_id=ivan,
        status="planned",
        starts_at=day_start.replace(hour=10, minute=0, tzinfo=UTC),
        duration_min=60,
    )
    lesson_factory(
        student_id=anna,
        status="completed",
        starts_at=day_start.replace(hour=12, minute=0, tzinfo=UTC),
        duration_min=60,
    )

    response = client.get("/tutor/")
    assert "Иван Иванов" in response.text
    assert "Анна Смирнова" in response.text
    # Предмет педагога — подпись строки (по референсу главной).
    assert "Английский язык" in response.text
    assert "10:00 - 11:00" in response.text
    assert "12:00 - 13:00" in response.text


def test_dashboard_schedule_crosses_midnight(
    client,
    tutor_factory,
    student_factory,
    lesson_factory,
):
    """Урок через полночь показывает переход «23:30 - 00:30», по референсу."""
    tutor_id = _login(client, tutor_factory, email="midnight@example.com")
    tutor = _tutor(tutor_id)
    day_start, _ = local_day_bounds(today_local(tutor), tutor)

    student = student_factory(tutor_id=tutor_id, first_name="Полуночный")
    lesson_factory(
        student_id=student,
        status="planned",
        starts_at=day_start.replace(hour=23, minute=30, tzinfo=UTC),
        duration_min=60,
    )

    response = client.get("/tutor/")
    assert "23:30 - 00:30" in response.text


def test_dashboard_recent_payments(
    client,
    tutor_factory,
    student_factory,
    operation_factory,
):
    """Блок платежей: имя, дата и сумма со знаком; ожидающий не попадает."""
    tutor_id = _login(client, tutor_factory, email="payments@example.com")
    tutor = _tutor(tutor_id)
    month_start = _month_noon(tutor)

    ivan = student_factory(tutor_id=tutor_id, first_name="Иван", last_name="Иванов")
    operation_factory(
        student_id=ivan,
        amount=2400,
        status="paid",
        occurred_at=month_start + timedelta(days=1),
    )
    operation_factory(student_id=ivan, amount=2000, status="paid", occurred_at=month_start)
    operation_factory(student_id=ivan, amount=5000, status="pending", occurred_at=month_start)

    response = client.get("/tutor/")
    assert "+2\u00a0400\u00a0₽" in response.text
    assert "+2\u00a0000\u00a0₽" in response.text
    assert "5\u00a0000\u00a0₽" not in response.text
    assert "Иван Иванов" in response.text

    # Дата свежего платежа — «день короткий-месяц» в зоне педагога.
    fresh = month_start + timedelta(days=1)
    assert f"{fresh.day} {_SHORT_MONTHS[fresh.month - 1]}" in response.text

    # Свежий платёж выше старого.
    assert response.text.index("+2\u00a0400\u00a0₽") < response.text.index("+2\u00a0000\u00a0₽")


def test_dashboard_isolation(
    client,
    tutor_factory,
    student_factory,
    lesson_factory,
    operation_factory,
):
    """Чужие ученики, уроки и платежи на главной не видны и не считаются."""
    _login(client, tutor_factory, email="mine-dash@example.com")

    stranger = student_factory(first_name="ЧужойУченикДашборда", status="active")
    lesson_factory(student_id=stranger, status="planned")
    operation_factory(student_id=stranger, amount=9999, status="paid")

    response = client.get("/tutor/")
    assert "ЧужойУченикДашборда" not in response.text
    assert "9\u00a0999\u00a0₽" not in response.text
    assert _stat_value(response.text, "Уроки сегодня") == "0"
    assert _stat_value(response.text, "Активные ученики") == "0"
    assert _stat_value(response.text, "Доход за месяц") == "0\u00a0₽"
    assert _stat_value(response.text, "Проведено часов") == "0"
    assert "На сегодня уроков нет" in response.text
    assert "Платежей пока нет" in response.text
