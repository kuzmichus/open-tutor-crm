"""Удаление урока и серии (спека lesson-management, «Удаление урока и серии»).

Уроки серии материализованы (решение D2), поэтому удаление серии —
это удаление всех уроков с её `series_id` и самой записи `LessonSeries`
одной транзакцией. Явное удаление уроков, а не надежда на каскад:
в тестовой БД SQLite PRAGMA foreign_keys может быть выключен.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_series import LessonSeries


def delete_lesson(db: Session, lesson: Lesson) -> None:
    """Удаляет один урок; у члена серии серия остаётся (уменьшается)."""
    db.delete(lesson)
    db.commit()


def delete_series(db: Session, series_id: str) -> int:
    """Удаляет все уроки серии и саму серию. Возвращает число уроков."""
    lessons = db.scalars(
        select(Lesson).where(Lesson.series_id == series_id)
    ).all()
    for lesson in lessons:
        db.delete(lesson)
    series = db.get(LessonSeries, series_id)
    if series is not None:
        db.delete(series)
    db.commit()
    return len(lessons)
