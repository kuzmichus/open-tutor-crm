"""Возраст ученика в миникарточке списка (change show-age-in-minicard).

Проверяются два слоя: чистая арифметика полных лет (`full_years`) и подпись
для шаблона (`student_age_label`) — склонение, отсутствие даты и граница
суток по часовому поясу педагога.
"""

from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.student.services.birthdays import full_years
from app.student.services.presentation import student_age_label

# --------------------------------------------------------------------------
# Полные годы
# --------------------------------------------------------------------------

def test_full_years_counts_only_completed_years():
    """День рождения в текущем году ещё не наступил — год не засчитан."""
    born = date(2014, 11, 3)
    assert full_years(born, date(2026, 11, 2)) == 11  # завтра исполнится 12
    assert full_years(born, date(2026, 11, 3)) == 12  # сегодня исполнилось 12
    assert full_years(born, date(2026, 11, 4)) == 12  # уже прошёл в этом году

def test_full_years_february_29_in_non_leap_year():
    """Рождение 29 февраля: полные годы прибавляются 1 марта.

    2028 — високосный (полный год наступает 29 февраля), 2029 — нет
    (28 февраля возраст ещё не полный, 1 марта — уже полный).
    """
    born = date(2028, 2, 29)
    assert full_years(born, date(2029, 2, 28)) == 0
    assert full_years(born, date(2029, 3, 1)) == 1
    assert full_years(born, date(2028, 2, 29)) == 0

def test_full_years_future_birth_date_is_unknown():
    """Дата рождения в будущем — возраст неизвестен, а не отрицательный."""
    assert full_years(date(2027, 1, 1), date(2026, 11, 2)) is None

# --------------------------------------------------------------------------
# Подпись возраста для шаблона
# --------------------------------------------------------------------------

def _tutor(timezone: str = "UTC"):
    """Минимальная карточка педагога: подписи нужна только зона."""
    return SimpleNamespace(timezone=timezone)

def test_student_age_label_pluralizes_years(monkeypatch):
    """Склонение: 1 год, 2 года, 5 лет, 11 лет, 21 год."""
    monkeypatch.setattr(
        "app.common.services.tutor_time.utcnow",
        lambda: datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
    )
    tutor = _tutor()
    assert student_age_label(date(2025, 11, 2), tutor) == "1 год"
    assert student_age_label(date(2024, 11, 2), tutor) == "2 года"
    assert student_age_label(date(2021, 11, 2), tutor) == "5 лет"
    assert student_age_label(date(2015, 11, 2), tutor) == "11 лет"
    assert student_age_label(date(2005, 11, 2), tutor) == "21 год"
    assert student_age_label(date(2014, 11, 2), tutor) == "12 лет"

def test_student_age_label_without_date_is_empty(monkeypatch):
    """Нет даты или она в будущем — пустая строка, подпись подтипа ставит шаблон."""
    monkeypatch.setattr(
        "app.common.services.tutor_time.utcnow",
        lambda: datetime(2026, 11, 2, 10, 0, tzinfo=UTC),
    )
    tutor = _tutor()
    assert student_age_label(None, tutor) == ""
    assert student_age_label(date(2027, 1, 1), tutor) == ""

def test_student_age_label_uses_tutor_timezone(monkeypatch):
    """Возраст считается по местной дате педагога, а не по UTC.

    В 22:30 UTC 2 ноября у педагога в UTC+04 уже 3 ноября: при дате
    рождения 3 ноября он показывает на год больше, чем педагог в UTC.
    """
    fixed = datetime(2026, 11, 2, 22, 30, tzinfo=UTC)
    monkeypatch.setattr("app.common.services.tutor_time.utcnow", lambda: fixed)

    born = date(2014, 11, 3)
    assert student_age_label(born, _tutor("Europe/Ulyanovsk")) == "12 лет"
    assert student_age_label(born, _tutor("UTC")) == "11 лет"
