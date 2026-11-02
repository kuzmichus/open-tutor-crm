"""Удаление урока и серии (спека lesson-management, «Удаление урока и серии»).

Уроки серии материализованы (решение D2), поэтому удаление серии —
это удаление всех уроков с её `series_id` и самой записи `LessonSeries`
одной транзакцией. Явное удаление уроков, а не надежда на каскад:
в тестовой БД SQLite PRAGMA foreign_keys может быть выключен.

Файлы ДЗ (спека file-storage, «Удаление урока уносит объекты файлов»):
каскад БД снимает строки `homework_files` и `files`, но объекты в хранилище
каскад не тронет — их удаляет `delete_homework_files` до удаления уроков.
Иначе файлы оставались бы в каталоге или бакете навсегда, уже без ключей в
базе.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.files.services.removal import delete_homework_files
from app.lesson.models.lesson import Lesson
from app.lesson.models.lesson_series import LessonSeries

def delete_lesson(db: Session, lesson: Lesson) -> None:
    """Удаляет один урок; у члена серии серия остаётся (уменьшается)."""
    delete_homework_files(db, [lesson.id])
    db.delete(lesson)
    db.commit()

def delete_series(db: Session, series_id: str) -> int:
    """Удаляет все уроки серии и саму серию. Возвращает число уроков."""
    lessons = db.scalars(
        select(Lesson).where(Lesson.series_id == series_id)
    ).all()
    delete_homework_files(db, [lesson.id for lesson in lessons])
    for lesson in lessons:
        db.delete(lesson)
    series = db.get(LessonSeries, series_id)
    if series is not None:
        db.delete(series)
    db.commit()
    return len(lessons)
