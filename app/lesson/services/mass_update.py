"""Массовое редактирование серии: общие поля формы — на все уроки.

Переключатель «Применить ко всей серии» (спека lesson-management):
включённый переключатель при сохранении применяет общие поля формы —
тип, цель (ученик или группа), длительность, ссылку на встречу и оплату
ученика — ко всем урокам серии, **включая прошедшие** (осознанное
решение, design: Risks).

Пер-уточные поля (статус, оценка, комментарий для семьи, заметка)
на серию НЕ распространяются: сервис принимает только whitelist
`MASS_UPDATE_FIELDS`, остальные ключи `data` игнорируются — в том числе
если форма прислала их вместе с включённым переключателем.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lesson.models.lesson import Lesson

# Общие поля формы, допустимые к массовому применению.
MASS_UPDATE_FIELDS = (
    "type",
    "student_id",
    "group_id",
    "duration_min",
    "meeting_url",
    "price",
)


def apply_to_series(db: Session, series_id: str, data: dict) -> int:
    """Применяет общие поля `data` ко всем урокам серии. Возвращает число уроков.

    Валидация (`validate_lesson_data`) — на стороне формы редактирования:
    здесь только применение белого списка полей. Применяются ключи,
    присланные в `data` (форма отправляет все поля, очистка — явный
    `None`); пер-уточные поля статуса, оценки, комментария и заметки
    не читаются вовсе.
    """
    values = {
        field: data[field] for field in MASS_UPDATE_FIELDS if field in data
    }
    lessons = db.scalars(
        select(Lesson).where(Lesson.series_id == series_id)
    ).all()
    for lesson in lessons:
        for field, value in values.items():
            setattr(lesson, field, value)
    db.commit()
    return len(lessons)
