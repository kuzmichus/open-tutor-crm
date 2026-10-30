"""Подстановки переменных в тексте сообщения.

Подстановка идёт на отправке, под конкретного ученика: в шаблоне хранится
исходный текст с токенами. Неизвестные токены остаются как есть — видны в
тексте, а не теряются молча.
"""

from datetime import datetime

from app.finance.services.presentation import balance_label
from app.student.models.student import Student
from app.student.services.presentation import next_lesson_label, student_full_name

# Поддерживаемые подстановки: ключ в тексте — человекочитаемая подпись
# для подсказки в композере.
PLACEHOLDERS: dict[str, str] = {
    "{имя}": "Имя ученика",
    "{баланс}": "Баланс ученика",
    "{следующий_урок}": "Следующий урок",
}

# Подпись, когда подстановка не имеет значения (уроков нет).
NO_VALUE = "—"


def render_message(
    text: str,
    *,
    student: Student,
    balance: int,
    next_lesson_at: datetime | None,
    tutor,
) -> str:
    """Подставляет значения ученика в текст; неизвестные токены целы."""
    replacements = {
        "{имя}": student_full_name(student) or student.first_name,
        "{баланс}": balance_label(balance),
        "{следующий_урок}": (
            next_lesson_label(next_lesson_at, tutor) or NO_VALUE
        ),
    }
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text
