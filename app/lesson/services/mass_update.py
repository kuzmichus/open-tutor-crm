"""Массовое редактирование серии: общие поля формы — на все уроки.

Переключатель «Применить ко всей серии» (спека lesson-management):
включённый переключатель при сохранении применяет общие поля формы —
тип, цель (ученик или группа), длительность, ссылку на встречу и оплату
ученика — ко всем урокам серии, **включая прошедшие** (осознанное
решение, design: Risks). Исключение — цена: проведённым урокам она
не применяется (спека «Цена проведённого урока только для чтения»).

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

    Цена — исключение из «включая прошедшие» (спека «Цена проведённого
    урока только для чтения»): проведённым урокам серии она не
    применяется, их списания остаются прежними; остальные общие поля
    меняются у всех.
    """
    lessons = db.scalars(
        select(Lesson).where(Lesson.series_id == series_id)
    ).all()
    for lesson in lessons:
        fields = MASS_UPDATE_FIELDS
        if lesson.status == "completed":
            fields = tuple(f for f in MASS_UPDATE_FIELDS if f != "price")
        for field in fields:
            if field in data:
                setattr(lesson, field, data[field])
    db.commit()
    return len(lessons)
