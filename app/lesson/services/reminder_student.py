"""Ученик — получатель напоминания о начале урока."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReminderStudent:
    """Ученик урока, которому включены напоминания об уроке.

    `timezone` — часовой пояс из карточки ученика; `None` означает
    «не задан», и время в сообщении показывается в зоне педагога.
    """

    student_id: str
    name: str
    timezone: str | None