"""Предстоящий урок для напоминания: когда, с кем и кому ещё писать."""

from dataclasses import dataclass
from datetime import datetime

from app.lesson.services.reminder_student import ReminderStudent


@dataclass(frozen=True)
class ReminderLesson:
    """Урок в окне напоминаний.

    `starts_at` — момент начала в UTC; в зону получателя его переводит
    сервис отправки, потому что у репетитора и ученика зоны разные.
    `target_name` — имя ученика или название группы: первая строка
    сообщения репетитору. `students` — только те участники, у которых
    включены напоминания (`remind_lesson`).
    """

    lesson_id: str
    starts_at: datetime
    is_group: bool
    target_name: str
    students: tuple[ReminderStudent, ...]