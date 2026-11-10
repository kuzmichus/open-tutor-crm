"""Сохранение домашнего задания урока (решение D1: ленивое создание).

Запись ДЗ создаётся при первом сохранении вкладки «ДЗ» и обновляется при
последующих — UNIQUE на `lesson_id` гарантирует ровно одну запись на урок.
Сохраняется только запись ДЗ: поля урока не изменяются (спека «Сохранение
ДЗ отдельно от урока»). При любой ошибке транзакция откатывается и в БД
не меняется ничего (design D4).

Срок сдачи нового ДЗ при пустом поле подставляется из начала следующего
занятия (`due_default.next_lesson_start`, TOCRM-62).

`commit=False` — режим вьюхи с файлами: запись ДЗ только сбрасывается
(`flush`), чтобы у неё появился id для привязки файлов, а коммит делает
вызывающий после успешной загрузки. Ошибка файла тогда откатывает и ДЗ, и
файлы одной транзакцией (design D5).

Сервис не знает про FastAPI: на вход — словарь очищенных значений
`parse_homework_form`, на выход — список ошибок (пустой при успехе).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.homework.models.homework import Homework
from app.homework.services.due_default import next_lesson_start
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

def save_homework(
    db: Session,
    lesson: Lesson,
    data: dict,
    *,
    commit: bool = True,
) -> list[str]:
    """Создаёт (лениво) или обновляет ДЗ урока; при ошибке — rollback.

    Проверки дублируются здесь (как в `lesson_writer`): форма могла быть
    отправлена криво или в обход разбора. Пустой статус — значение по
    умолчанию «Не задано».

    `commit=False` — запись сбрасывается, но не коммитится: вьюха прикрепляет
    файлы и коммитит сама (или откатывает всё при ошибке файла).

    Новое ДЗ без указанного срока получает начало следующего занятия
    (`next_lesson_start`, TOCRM-62): форма без JS присылает пустое поле, и
    полагаться на предзаполнение в браузере нельзя. У существующей записи
    срок берётся из формы как есть — очищенный вручную остаётся пустым.
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
        if values["due_at"] is None:
            values["due_at"] = next_lesson_start(db, lesson)
        db.add(Homework(lesson_id=lesson.id, **values))
    else:
        for field in _VALUE_FIELDS:
            setattr(homework, field, values[field])

    if commit:
        db.commit()
    else:
        # id нужен привязке файлов — flush выдаёт его без коммита.
        db.flush()
    return []
