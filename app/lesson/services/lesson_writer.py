"""Запись урока: одиночный урок и материализация серии (решение D2).

Сохранение атомарно: либо создаются все записи серии (серия + уроки),
либо не создаётся ничего — при ошибке транзакция откатывается.
Проверки дублируются здесь (как в group_writer): форма могла быть
отправлена криво или устаревшими данными.

Сервис не знает про FastAPI: на вход — словарь с очищенными значениями
формы, на выход — результат и список ошибок. Ожидаемые ключи `data`:

- общие: `student_id`, `group_id`, `type`, `starts_at`, `duration_min`,
  `note`, `meeting_url`, `price`;
- только серия: `repeat`, `slots`, `interval_weeks`, `until_date`.

Поля статуса, оценки и комментария для семьи при создании не принимаются:
новой серии и уроку присваивается статус «Запланирован» (спека), статус
и блок «Для семьи» меняются при редактировании.
"""

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.lesson.models.lesson import LESSON_DURATIONS, LESSON_TYPES, Lesson
from app.lesson.models.lesson_series import LessonSeries
from app.lesson.services.series_generator import generate_occurrences


def validate_lesson_data(data: dict) -> list[str]:
    """Проверки создания урока: начало, цель по типу, длительность, повтор."""
    errors: list[str] = []

    if data.get("starts_at") is None:
        errors.append("Укажите начало урока.")

    # Цель по типу урока (решение D3): групповой → группа, остальные → ученик.
    lesson_type = data.get("type")
    if lesson_type not in LESSON_TYPES:
        errors.append("Выберите тип урока.")
    elif lesson_type == "group":
        if data.get("student_id"):
            errors.append("Для группового урока выберите группу, а не ученика.")
        elif not data.get("group_id"):
            errors.append("Выберите группу для группового урока.")
    else:
        if data.get("group_id"):
            errors.append("Для этого типа урока выберите ученика, а не группу.")
        elif not data.get("student_id"):
            errors.append("Выберите ученика для урока.")

    if data.get("duration_min") not in LESSON_DURATIONS:
        errors.append("Выберите длительность урока из списка.")

    if data.get("repeat"):
        # Повтор без даты окончания запрещён (спека); она же закрывает
        # «бесконечную» серию (решение D2).
        starts_at: datetime | None = data.get("starts_at")
        until_date: date | None = data.get("until_date")
        if until_date is None:
            errors.append("Укажите дату окончания повтора.")
        elif starts_at is not None and until_date < starts_at.date():
            errors.append("Дата окончания повтора не раньше начала урока.")
        if (data.get("interval_weeks") or 1) < 1:
            errors.append("Интервал повтора — не менее одной недели.")
        if not data.get("slots"):
            errors.append("Панель расписания пуста: добавьте хотя бы один слот.")

    return errors


def _new_lesson(data: dict, *, series_id: str | None, starts_at: datetime) -> Lesson:
    """Урок из данных формы: цель, время, длительность и «мелочи»."""
    return Lesson(
        student_id=data.get("student_id"),
        group_id=data.get("group_id"),
        series_id=series_id,
        type=data["type"],
        starts_at=starts_at,
        duration_min=data["duration_min"],
        note=data.get("note") or None,
        meeting_url=data.get("meeting_url") or None,
        price=data.get("price"),
    )


def create_single_lesson(db: Session, data: dict) -> tuple[Lesson | None, list[str]]:
    """Создаёт один урок без серии; при ошибке ничего не сохраняет."""
    errors = validate_lesson_data(data)
    if errors:
        db.rollback()
        return None, errors

    lesson = _new_lesson(data, series_id=None, starts_at=data["starts_at"])
    db.add(lesson)
    db.commit()
    return lesson, []


def create_series(db: Session, data: dict) -> tuple[list[Lesson], list[str]]:
    """Создаёт серию одним коммитом: `LessonSeries` + уроки на все даты.

    Даты считаются генератором (слоты → даты от начала через интервал
    недель до окончания включительно); длительность уроков — из поля
    «Длительность» формы. При ошибке (пустые слоты, кривой слот, отмена
    валидации) не сохраняется ни серия, ни уроки.
    """
    errors = validate_lesson_data(data)
    if errors:
        db.rollback()
        return [], errors

    interval_weeks = data.get("interval_weeks") or 1
    until_date: date = data["until_date"]
    try:
        occurrences = generate_occurrences(
            starts_at=data["starts_at"],
            slots=data["slots"],
            interval_weeks=interval_weeks,
            until_date=until_date,
        )
    except ValueError as exc:
        db.rollback()
        return [], [str(exc)]

    series = LessonSeries(
        slots=data["slots"],
        interval_weeks=interval_weeks,
        until_date=until_date,
    )
    db.add(series)
    db.flush()

    lessons = [
        _new_lesson(data, series_id=series.id, starts_at=starts_at)
        for starts_at in occurrences
    ]
    db.add_all(lessons)
    db.commit()
    return lessons, []


def update_lesson(db: Session, lesson: Lesson, data: dict) -> list[str]:
    """Применяет данные формы редактирования к одному уроку (без коммита).

    Пер-уточные поля (статус, оценка, комментарий для семьи, заметка)
    применяются только к этому уроку; массовое применение общих полей
    серии — `mass_update.apply_to_series`. Коммит делает вызывающая
    сторона: при включённом «Применить ко всей серии» одной транзакцией
    проходят и урок, и вся серия.
    """
    errors = validate_lesson_data(data)
    if errors:
        db.rollback()
        return errors

    lesson.student_id = data.get("student_id")
    lesson.group_id = data.get("group_id")
    lesson.type = data["type"]
    lesson.starts_at = data["starts_at"]
    lesson.duration_min = data["duration_min"]
    lesson.note = data.get("note") or None
    lesson.meeting_url = data.get("meeting_url") or None
    lesson.price = data.get("price")
    if data.get("status"):
        lesson.status = data["status"]
    lesson.rating = data.get("rating")
    lesson.family_comment = data.get("family_comment") or None
    return []
