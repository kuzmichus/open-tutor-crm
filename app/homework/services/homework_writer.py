"""Сохранение домашнего задания урока (решение D1: ленивое создание).

Запись ДЗ создаётся при первом сохранении вкладки «ДЗ» и обновляется при
последующих — UNIQUE на `lesson_id` гарантирует ровно одну запись на урок.
Сохраняется только запись ДЗ: поля урока не изменяются (спека «Сохранение
ДЗ отдельно от урока»). При любой ошибке транзакция откатывается и в БД
не меняется ничего (design D4).

Сервис не знает про FastAPI: на вход — словарь очищенных значений
`parse_homework_form`, на выход — список ошибок (пустой при успехе).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.homework.models.homework import Homework
from app.homework.services.homework_form import validate_homework_data
from app.lesson.models.lesson import Lesson

# Копируемые поля: ровно те, что приходят из формы панели ДЗ.
_VALUE_FIELDS = (
    "assignment",
    "due_at",
    "deadline_enabled",
    "status",
    "recording_url",
    "teacher_note",
    "teacher_comment",
)


def get_homework(db: Session, lesson_id: str) -> Homework | None:
    """Запись ДЗ урока или None (ленивое создание — записи ещё нет)."""
    return db.scalars(
        select(Homework).where(Homework.lesson_id == lesson_id)
    ).one_or_none()


def save_homework(db: Session, lesson: Lesson, data: dict) -> list[str]:
    """Создаёт (лениво) или обновляет ДЗ урока; при ошибке — rollback.

    Проверки дублируются здесь (как в `lesson_writer`): форма могла быть
    отправлена криво или в обход разбора. Пустой статус — значение по
    умолчанию «Не задано».
    """
    errors = validate_homework_data(data)
    if errors:
        db.rollback()
        return errors

    values = {
        "assignment": (data.get("assignment") or "").strip(),
        "due_at": data.get("due_at"),
        "deadline_enabled": bool(data.get("deadline_enabled")),
        "status": data.get("status") or "not_assigned",
        "recording_url": data.get("recording_url"),
        "teacher_note": data.get("teacher_note"),
        "teacher_comment": data.get("teacher_comment"),
    }

    homework = get_homework(db, lesson.id)
    if homework is None:
        db.add(Homework(lesson_id=lesson.id, **values))
    else:
        for field in _VALUE_FIELDS:
            setattr(homework, field, values[field])

    db.commit()
    return []
