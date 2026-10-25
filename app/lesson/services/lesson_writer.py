"""Запись урока: одиночный урок и материализация серии (решение D2).

Сохранение атомарно: либо создаются все записи серии (серия + уроки),
либо не создаётся ничего — при ошибке транзакция откатывается.
Проверки дублируются здесь (как в group_writer): форма могла быть
отправлена криво или устаревшими данными.

Сервис не знает про FastAPI: на вход — словарь с очищенными значениями
формы, на выход — результат и список ошибок. Ожидаемые ключи `data`:

- общие: `student_id`, `group_id`, `type`, `starts_at` (aware UTC —
  форма переводит его по зоне педагога, design D6), `duration_min`,
  `note`, `meeting_url`, `price`;
- только серия: `repeat`, `slots`, `interval_weeks`, `until_date`.

Поля статуса, оценки и комментария для семьи при создании не принимаются:
новой серии и уроку присваивается статус «Запланирован» (спека), статус
и блок «Для семьи» меняются при редактировании.
"""

from datetime import date, datetime

from sqlalchemy.orm import Session

from app.common.services.tutor_time import to_local, to_utc
from app.finance.services.charges import sync_lesson_charge
from app.lesson.models.lesson import LESSON_DURATIONS, LESSON_TYPES, Lesson
from app.lesson.models.lesson_series import LessonSeries
from app.lesson.services.series_generator import generate_occurrences


def validate_lesson_data(data: dict, tutor) -> list[str]:
    """Проверки создания урока: начало, цель по типу, длительность, повтор.

    Даты сравниваются в зоне педагога: `starts_at` хранится в UTC, а
    «дата окончания повтора» — чистая календарная дата (design D3).
    """
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
        elif starts_at is not None and until_date < to_local(starts_at, tutor).date():
            errors.append("Дата окончания повтора не раньше начала урока.")
        if (data.get("interval_weeks") or 1) < 1:
            errors.append("Интервал повтора — не менее одной недели.")
        if not data.get("slots"):
            errors.append("Панель расписания пуста: добавьте хотя бы один слот.")

    return errors


def _new_lesson(data: dict, *, series_id: str | None, starts_at: datetime) -> Lesson:
    """Урок из данных формы: цель, время, длительность и «мелочи».

    Статус при создании не приходит из формы (поля «Проведение» на
    создании нет), поэтому по умолчанию урок «Запланирован». Явно
    переданный статус принимается: этим путём проведённый урок создаётся
    сразу с занятием и списанием (тесты, будущие импорты).
    """
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
        status=data.get("status") or "planned",
    )


def create_single_lesson(
    db: Session, data: dict, tutor
) -> tuple[Lesson | None, list[str]]:
    """Создаёт один урок без серии; при ошибке ничего не сохраняет.

    `data["starts_at"]` уже aware UTC (разбор формы) — повторный перевод
    здесь не нужен (design D6).

    Списание создаётся до `commit`: урок и его операция счёта сохраняются
    одной транзакцией (design D6). Проведённый урок без цены списания не
    создаёт — это решает `sync_lesson_charge`.
    """
    errors = validate_lesson_data(data, tutor)
    if errors:
        db.rollback()
        return None, errors

    lesson = _new_lesson(data, series_id=None, starts_at=data["starts_at"])
    db.add(lesson)
    # `flush` нужен до синхронизации: у строки должен быть `id`, на который
    # ссылается `account_operations.lesson_id`.
    db.flush()
    sync_lesson_charge(db, lesson)
    db.commit()
    return lesson, []


def create_series(db: Session, data: dict, tutor) -> tuple[list[Lesson], list[str]]:
    """Создаёт серию одним коммитом: `LessonSeries` + уроки на все даты.

    Даты считаются генератором в настенном времени зоны педагога (дни
    недели и `until_date` — локальные, design D5), поэтому UTC-начало
    формы сначала переводится обратно в локальное наивное значение. Каждая
    сгенерированная дата конвертируется в UTC **отдельно**: прибавление
    недели к UTC-значению сдвигало бы уроки в неделю с переводом часов
    (design D3/D5). Длительность уроков — из поля «Длительность» формы.
    При ошибке (пустые слоты, крой слот, отмена валидации) не сохраняется
    ни серия, ни уроки.
    """
    errors = validate_lesson_data(data, tutor)
    if errors:
        db.rollback()
        return [], errors

    interval_weeks = data.get("interval_weeks") or 1
    until_date: date = data["until_date"]
    try:
        occurrences = generate_occurrences(
            starts_at=to_local(data["starts_at"], tutor).replace(tzinfo=None),
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
        _new_lesson(data, series_id=series.id, starts_at=to_utc(occurrence, tutor))
        for occurrence in occurrences
    ]
    db.add_all(lessons)
    # `flush` до синхронизации: списанию нужен `id` урока. Серия коммитится
    # одним разом вместе со всеми списаниями (design D6).
    db.flush()
    for lesson in lessons:
        sync_lesson_charge(db, lesson)
    db.commit()
    return lessons, []


def update_lesson(db: Session, lesson: Lesson, data: dict, tutor) -> list[str]:
    """Применяет данные формы редактирования к одному уроку (без коммита).

    `data["starts_at"]` уже aware UTC. Пер-уточные поля (статус, оценка,
    комментарий для семьи, заметка) применяются только к этому уроку;
    массовое применение общих полей серии — `mass_update.apply_to_series`.
    Коммит делает вызывающая сторона: при включённом «Применить ко всей
    серии» одной транзакцией проходят и урок, и вся серия.
    """
    errors = validate_lesson_data(data, tutor)
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
    # Цена проведённого урока заморожена (спека «Цена проведённого урока
    # только для чтения»): поле в форме показывается, но присланные значения
    # игнорируются — история счёта не переписывается постфактум. Перевод
    # «Запланирован» → «Проведён» цену применяет: списание создаётся по ней.
    lesson.price = (
        lesson.price if lesson.status == "completed" else data.get("price")
    )
    if data.get("status"):
        lesson.status = data["status"]
    lesson.rating = data.get("rating")
    lesson.family_comment = data.get("family_comment") or None
    return []
