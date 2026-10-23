"""Запись отметок недоступности: создание, изменение срока, снятие.

Сервис не знает про FastAPI: на вход — `Session`, `tutor_id` и очищенные
значения формы, на выход — отметка или список ошибок (пустой при успехе).
Проверки дублируются здесь (как в `lesson_writer`): форма могла быть
отправлена в обход разбора, а инварианты обязаны держаться и в БД.

«Изменить срок» меняет только последний день (design.md D9): причина и
первый день остаются как были — снимать и ставить отметку заново не нужно.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.unavailability.models.unavailability import (
    DAYOFF_REASON,
    TutorUnavailability,
)
from app.unavailability.services.unavailability_form import (
    validate_end_change,
    validate_unavailability_data,
)


def _values(data: dict) -> dict:
    """Поля записи по режиму: чужие поля режима всегда NULL (CHECK БД).

    Причина постоянного выходного не берётся из формы: у него она одна
    (спека «Режим „Постоянный выходной“ задаёт день недели»).
    """
    if data.get("mode") == "weekday":
        return {
            "mode": "weekday",
            "reason": DAYOFF_REASON,
            "start_date": None,
            "end_date": None,
            "weekday": data.get("weekday"),
            "until_date": data.get("until_date"),
        }
    return {
        "mode": "period",
        "reason": data.get("reason"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
        "weekday": None,
        "until_date": None,
    }


def create_mark(db: Session, tutor_id: str, data: dict) -> tuple[object, list[str]]:
    """Создаёт отметку; при ошибке ничего не сохраняет."""
    errors = validate_unavailability_data(data)
    if errors:
        db.rollback()
        return None, errors

    mark = TutorUnavailability(tutor_id=tutor_id, **_values(data))
    db.add(mark)
    db.commit()
    return mark, []


def change_end(
    db: Session, mark: TutorUnavailability, new_end: date | None
) -> list[str]:
    """Меняет только срок отметки: `end_date` периода или `until_date` выходного.

    Пустое значение — бессрочно (период) / без ограничения (выходной).
    Причина и первый день не меняются (design.md D9).
    """
    errors = validate_end_change(mark, new_end)
    if errors:
        db.rollback()
        return errors

    if mark.mode == "period":
        mark.end_date = new_end
    else:
        mark.until_date = new_end
    db.commit()
    return []


def delete_mark(db: Session, mark: TutorUnavailability) -> None:
    """Снимает отметку: отмеченные ею дни снова считаются доступными."""
    db.delete(mark)
    db.commit()
