"""Подсказки городов для поля «Город» в карточке ученика.

Справочника городов в проекте нет: город — свободный текст, а список
подсказок собирается из уже введённых городов других учеников этого
репетитора. Так репетитор видит привычные ему написания и не заводит
«Москва»/«москва»/«г. Москва» в трёх вариантах.

Сравнение — в Python по `casefold()`: SQLite `lower()` не понимает
кириллицу (тот же приём, что в поиске учеников, `students._matches_search`).
"""

from json import dumps

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.student.models.student import Student


def city_options(
    db: Session,
    tutor_id: str,
    exclude_student_id: str | None = None,
) -> list[dict]:
    """Города других учеников репетитора: `[{value, label}, ...]`.

    `exclude_student_id` — ученик, чья карточка открыта: его собственный
    город в подсказки не попадает («города других учеников»). Дубликаты
    схлопываются без учёта регистра — остаётся первое написание.
    `label` пустой: у города нет второй колонки, а виджет `combobox`
    вторую колонку просто не рисует.
    """
    stmt = select(Student.city).where(
        Student.tutor_id == tutor_id,
        Student.city.is_not(None),
        Student.city != "",
    )
    if exclude_student_id:
        stmt = stmt.where(Student.id != exclude_student_id)

    seen: set[str] = set()
    values: list[str] = []
    for city in db.scalars(stmt).all():
        key = city.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(city)

    values.sort(key=str.casefold)
    return [{"value": city, "label": ""} for city in values]


def city_options_json(
    db: Session,
    tutor_id: str,
    exclude_student_id: str | None = None,
) -> str:
    """JSON-массив городов для `data-options` формы (как часовые зоны)."""
    return dumps(
        city_options(db, tutor_id, exclude_student_id),
        ensure_ascii=False,
        separators=(",", ":"),
    )
