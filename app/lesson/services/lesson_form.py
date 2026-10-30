"""Разбор формы урока и контекст модального окна (создание и редактирование).

Форма одна на оба режима (`lesson/_form.html`):
- в создании есть панель расписания («Повторять урок»), поля статуса,
  оценки и комментария для семьи отсутствуют — создание их игнорирует
  (решение задачи 2.2);
- в редактировании серия полем не управляется (генерация серии — только
  при создании, design: Non-Goals; решение пользователя), зато есть
  статус, блок «Для семьи» и переключатель «Применить ко всей серии».

Слоты формы приходят одним скрытым полем `slots` — JSON-списком
объектов `{weekday, start_time, end_time}` (решение D1, тот же формат,
что хранится в `lesson_series.slots`).
"""

import json
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.forms import checked, int_or_none, text_value
from app.common.services.tutor_time import to_local, to_utc
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.homework.services.homework_context import homework_panel_context
from app.lesson.models.lesson import (
    LESSON_DURATIONS,
    LESSON_STATUS_LABELS,
    LESSON_STATUSES,
    LESSON_TYPE_LABELS,
    MAX_LESSON_RATING,
    MIN_LESSON_RATING,
)
from app.lesson.models.lesson_attendance import (
    ABSENCE_REASON_LABELS,
    ABSENCE_REASONS,
    LessonAttendance,
)
from app.lesson.services.presentation import (
    format_lesson_datetime,
    format_target,
    format_time_span,
)
from app.lesson.services.until_presets import until_presets
from app.student.models.student import Student
from app.student.services.presentation import student_full_name

# Дни недели панели расписания: `weekday` 0 = понедельник … 6 = воскресенье.
WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

# Обычный контейнер модалки урока (страница уроков, календарь); второй
# слой `#modal-lesson` (design D10) — окно поверх модалки группы.
DEFAULT_MODAL_TARGET = "#modal"


def _parse_datetime(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_price(raw: str) -> tuple[int | None, bool]:
    """Оплата ученика: (значение, ошибка разбора). Пусто — None без ошибки."""
    if raw == "":
        return None, False
    value = int_or_none(raw)
    if value is None or value < 0:
        return None, True
    return value, False


def _rating_value(raw: str):
    """Оценка «как пришла»: int, None (пусто) или строка-мусор для ошибки."""
    if raw == "":
        return None
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw


def _parse_slots(raw: str) -> list[dict] | None:
    """Слоты формы → формат D1; некорректный список — None («панель пуста»)."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, list) or not parsed:
        return None
    slots: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        weekday = item.get("weekday")
        if isinstance(weekday, str) and weekday.isdigit():
            weekday = int(weekday)
        if (
            isinstance(weekday, bool)
            or not isinstance(weekday, int)
            or not 0 <= weekday <= 6
        ):
            return None
        try:
            time.fromisoformat(str(item.get("start_time")))
            time.fromisoformat(str(item.get("end_time")))
        except ValueError:
            return None
        slots.append(
            {
                "weekday": weekday,
                "start_time": str(item["start_time"]),
                "end_time": str(item["end_time"]),
            }
        )
    return slots


def parse_starts_at(raw: str | None, tutor) -> datetime | None:
    """Значение `?starts_at=` из календаря: aware UTC или None.

    Пустой или некорректный параметр — не ошибка: форма открывается с
    пустым «Началом» (спека lesson-management, «Префилл из календаря»).
    Валидное значение трактуется как настенное время в зоне педагога и
    переводится в UTC сразу при разборе (design D6).
    """
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return to_utc(parsed, tutor)


def parse_duration_min(raw: str | None) -> int | None:
    """Значение `?duration_min=` из окна для записи: минуты из закрытого списка.

    Запись из окна создаёт урок той же длительности (спека calendar,
    «Запись ученика из свободного окна»), поэтому префилл обязан попасть
    в `LESSON_DURATIONS` — иначе форма открылась бы с невыделенным
    селектом, а урок сохранился бы с чужим значением. Всё, что вне
    списка, игнорируется: префилл — удобство, а не источник истины.
    """
    value = int_or_none((raw or "").strip())
    if value is None or value not in LESSON_DURATIONS:
        return None
    return value


def parse_attendance(raw: str | None) -> tuple[list[dict] | None, bool]:
    """Скрытое поле `attendance` → список отметок; `(значение, ошибка)`.

    Структурная проверка (design D7): JSON-список объектов
    `{student_id, present, reason}`, у каждого объекта непустой
    `student_id`, булев `present`, а `reason` — из `ABSENCE_REASONS` и
    только у отсутствовавших. Неполные записи — ошибка формы: молчаливый
    пропуск отметил бы участника присутствовавшим против воли репетитора.

    Состав группы здесь не проверяется (нет сессии): чужие и вышедшие id
    отсеивает `lesson_writer` — форма могла быть открыта до выхода
    участника. Отсутствие поля (создание урока, сохранение без JS) — не
    ошибка и не очистка: отметки просто не трогаются.
    """
    if raw is None or raw == "":
        return None, False
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None, True
    if not isinstance(parsed, list):
        return None, True
    records: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None, True
        student_id = item.get("student_id")
        present = item.get("present")
        reason = item.get("reason")
        if not isinstance(student_id, str) or not student_id:
            return None, True
        if not isinstance(present, bool):
            return None, True
        if present:
            # У присутствовавшего причины нет: чекбокс её сбрасывает, а
            # подделанное поле не должно проскочить в БД.
            if reason not in (None, ""):
                return None, True
            records.append({"student_id": student_id, "present": True, "reason": None})
        else:
            if reason not in ABSENCE_REASONS:
                return None, True
            records.append({"student_id": student_id, "present": False, "reason": reason})
    return records, False


def parse_lesson_form(form, tutor) -> tuple[dict, list[str]]:
    """Данные формы урока и ошибки разбора полей.

    `starts_at` приходит наивным (`datetime-local`) и сразу переводится в
    aware UTC по зоне педагога (design D6): дальше по цепочке
    (`lesson_writer`, предупреждения) время уже в UTC — повторно его не
    переводит ни один сервис.

    `rating` остаётся «как пришло» (int, None или мусор): проверка 1–5 —
    на стороне редактирования (`validate_edit_fields`), создание поле
    игнорирует вовсе.
    """
    errors: list[str] = []
    price, price_error = _parse_price(text_value(form, "price"))
    if price_error:
        errors.append("Оплата ученика — целое число не меньше нуля.")

    attendance, attendance_error = parse_attendance(text_value(form, "attendance"))
    if attendance_error:
        errors.append("Посещаемость: неверный формат данных.")

    starts_at = _parse_datetime(text_value(form, "starts_at"))
    data = {
        "student_id": text_value(form, "student_id") or None,
        "group_id": text_value(form, "group_id") or None,
        "type": text_value(form, "type"),
        "starts_at": to_utc(starts_at, tutor) if starts_at is not None else None,
        "duration_min": int_or_none(text_value(form, "duration_min")),
        "note": text_value(form, "note") or None,
        "meeting_url": text_value(form, "meeting_url") or None,
        "price": price,
        "repeat": bool(text_value(form, "repeat")),
        "interval_weeks": int_or_none(text_value(form, "interval_weeks")),
        "until_date": _parse_date(text_value(form, "until_date")),
        "slots": _parse_slots(text_value(form, "slots")),
        # Отметки присутствия (design D7): None — поле не пришло (создание,
        # сохранение без JS), список — прислали; состав группы проверит
        # writer. При ошибке формата здесь None — сохранение не дойдёт до
        # отметок из-за непустого errors.
        "attendance": attendance,
        "status": text_value(form, "status") or None,
        "rating": _rating_value(text_value(form, "rating")),
        "family_comment": text_value(form, "family_comment") or None,
        # Признак подтверждения, а не поле урока (design.md D5, п. 2):
        # относится только к этой отправке и в запись урока не попадает.
        "ack_unavailable": checked(form, "ack_unavailable"),
    }
    return data, errors


def validate_targets(db: Session, tutor_id: str, data: dict) -> list[str]:
    """Цель урока должна принадлежать вошедшему репетитору (спека: изоляция).

    Без проверки чужой репетитор мог бы «подложить» урок чужому ученику
    или группе — он попал бы в их список. Несуществующая и чужая цель
    неразличимы: одна ошибка.
    """
    errors: list[str] = []
    student_id = data.get("student_id")
    if student_id is not None:
        student = db.get(Student, student_id)
        if student is None or student.tutor_id != tutor_id:
            errors.append("Ученик не найден.")
    group_id = data.get("group_id")
    if group_id is not None:
        group = db.get(Group, group_id)
        if group is None or group.tutor_id != tutor_id:
            errors.append("Группа не найдена.")
    return errors


def validate_edit_fields(data: dict) -> list[str]:
    """Проверки полей редактирования, которых нет при создании."""
    errors: list[str] = []
    status_value = data.get("status")
    if status_value is not None and status_value not in LESSON_STATUSES:
        errors.append("Выберите статус урока.")
    rating = data.get("rating")
    if rating is not None and (
        isinstance(rating, bool)
        or not isinstance(rating, int)
        or not MIN_LESSON_RATING <= rating <= MAX_LESSON_RATING
    ):
        errors.append(f"Оценка — от {MIN_LESSON_RATING} до {MAX_LESSON_RATING} звёзд.")
    return errors


def _input_datetime(value, tutor) -> str:
    """Значение для `input[type=datetime-local]`: «YYYY-MM-DDTHH:MM».

    Значение (aware UTC из разбора или из БД) переводится в зону педагога
    перед показом (спека lesson-management, «Значение поля «Начало»»):
    поле формы всегда показывает настенное время педагога.
    """
    if isinstance(value, datetime):
        return to_local(value, tutor).strftime("%Y-%m-%dT%H:%M")
    return str(value or "")


def _form_values(lesson, data: dict | None, tutor) -> dict:
    """Значения полей формы из урока (правка) или из разбора (ошибка)."""
    if lesson is not None:
        return {
            "type": lesson.type,
            "duration_min": lesson.duration_min,
            "note": lesson.note,
            "meeting_url": lesson.meeting_url,
            "starts_at_value": _input_datetime(lesson.starts_at, tutor),
            "price": str(lesson.price) if lesson.price is not None else "",
            "until_date": "",
            "status": lesson.status,
            "rating": lesson.rating,
            "family_comment": lesson.family_comment,
        }
    data = data or {}
    price = data.get("price")
    return {
        "type": data.get("type") or "individual",
        "duration_min": data.get("duration_min"),
        "note": data.get("note"),
        "meeting_url": data.get("meeting_url"),
        "starts_at_value": _input_datetime(data.get("starts_at"), tutor),
        "price": str(price) if price is not None else "",
        "until_date": data.get("until_date") or "",
        "status": data.get("status") or (lesson.status if lesson else None),
        "rating": data.get("rating"),
        "family_comment": data.get("family_comment"),
    }


def _attendance_participants(db: Session, lesson) -> list[dict]:
    """Участники блока «Присутствие»: текущий состав + сохранённые отметки.

    Список строится из текущего состава группы (design D8): вышедший
    участник в блоке не показывается, его отметка в БД не трогается.
    Участник без отметки — присутствовал (design D2: нет отметок = все
    пришли), отметка присутствовавшего хранится, но на деньги не влияет.
    """
    marks = {
        mark.student_id: mark
        for mark in db.scalars(
            select(LessonAttendance).where(
                LessonAttendance.lesson_id == lesson.id
            )
        ).all()
    }
    students = db.scalars(
        select(Student)
        .join(GroupMember, GroupMember.student_id == Student.id)
        .where(GroupMember.group_id == lesson.group_id)
    ).all()
    participants = []
    for student in sorted(students, key=student_full_name):
        mark = marks.get(student.id)
        present = mark.present if mark is not None else True
        participants.append(
            {
                "student_id": student.id,
                "name": student_full_name(student),
                "present": present,
                # Причина есть только у отсутствовавшего (инвариант CHECK).
                "reason": mark.reason if mark is not None and not present else None,
            }
        )
    return participants


def lesson_form_context(
    db: Session,
    *,
    tutor,
    lesson=None,
    data: dict | None = None,
    errors: list[str] | None = None,
    unavailable_warning: dict | None = None,
    ack_unavailable: bool = False,
    modal_target: str = DEFAULT_MODAL_TARGET,
) -> dict:
    """Контекст `lesson/_form.html`: `lesson=None` — создание, иначе правка.

    `tutor` — карточка репетитора: её зона определяет значения полей
    «Начало» и подписи времени (спека tutor-timezone, «Показ времени идёт
    в зоне педагога»).

    При ошибке валидации переданные `data` перекрывают значения урока —
    модалка показывает присланные пользователем поля, а не старые.

    `unavailable_warning` — баннер предупреждения о постановке в отмеченный
    день (`warning_context`): отдельный ключ контекста, **не** элемент
    `errors` — предупреждение означает «сохранится, если подтвердите», а
    список ошибок — «не сохранено и не сохранится» (design.md D5, п. 3).
    `ack_unavailable` — скрытое поле подтверждения, чтобы повторная отправка
    не спрашивала снова (design.md D5, п. 4).

    `modal_target` — контейнер модалки для `hx-target` сохранения и
    удаления: обычный слой `#modal` либо второй слой (`#modal-lesson`,
    design D10), когда окно открыто поверх модалки группы из вкладки
    «Занятия» — повторная отрисовка с ошибкой и удаление должны
    подменять окно там же, где оно открыто.
    """
    values = _form_values(lesson, data, tutor)

    # Блок «Присутствие»: только у существующего группового урока (в
    # создании блока нет — участников ещё не выбрать). Один расчёт на
    # контекст: участники идут и в шаблон, и в Alpine-конфиг.
    attendance_participants = (
        _attendance_participants(db, lesson)
        if lesson is not None and lesson.type == "group" and lesson.group_id
        else []
    )

    if lesson is not None:
        student_name = _target_student_name(db, lesson.student_id)
        group_name = _target_group_name(db, lesson.group_id)
        student_id = lesson.student_id
        group_id = lesson.group_id
        action = f"/tutor/lessons/{lesson.id}"
        title = format_target(student_name, group_name, lesson.type)
        title = f"{title} · {format_lesson_datetime(lesson.starts_at, tutor)}"
        subtitle = format_time_span(lesson, tutor)
    else:
        student_id = data.get("student_id") if data else None
        group_id = data.get("group_id") if data else None
        student_name = _target_student_name(db, student_id)
        group_name = _target_group_name(db, group_id)
        action = "/tutor/lessons"
        title = "Новый урок"
        subtitle = ""

    return {
        "title": title,
        "subtitle": subtitle,
        "action": action,
        "modal_target": modal_target,
        "errors": errors or [],
        "form": values,
        "student_id": student_id or "",
        "student_name": student_name,
        "group_id": group_id or "",
        "group_name": group_name,
        "lesson": lesson,
        "series_id": lesson.series_id if lesson is not None else None,
        "type_labels": LESSON_TYPE_LABELS,
        "durations": LESSON_DURATIONS,
        "statuses": LESSON_STATUSES,
        "status_labels": LESSON_STATUS_LABELS,
        "weekdays": WEEKDAY_LABELS,
        "rating_stars": (1, 2, 3, 4, 5),
        "show_repeat": lesson is None,  # серия настраивается только при создании
        # Пресеты «До даты» нужны только там, где есть панель расписания:
        # в редактировании серия не управляется (design: Non-Goals).
        "until_presets": until_presets(db, tutor) if lesson is None else [],
        # Цена проведённого урока — только для чтения (и в форме, и на
        # сервере, см. lesson_writer): предупреждение о пересчёте не нужно.
        "price_locked": lesson is not None and lesson.status == "completed",
        # Пустой список скрывает блок и у группового урока без состава.
        "attendance_participants": attendance_participants,
        "absence_reasons": ABSENCE_REASONS,
        "absence_reason_labels": ABSENCE_REASON_LABELS,
        "form_config": {
            "type": values["type"],
            # Alpine-состояние блока «Присутствие» (design D6): участники
            # и сохранённые отметки приходят конфигом, как у слотов.
            "attendance": attendance_participants,
        },
        # Баннер недоступности: отдельно от `errors` (design.md D5, п. 3).
        "unavailable_warning": unavailable_warning or {},
        "ack_unavailable": ack_unavailable,
        # Контекст панели ДЗ (ключи `hw_*`) — только в редактировании:
        # вкладка «ДЗ» и её форма в создании отсутствуют (спека).
        **(
            homework_panel_context(db, lesson=lesson, tutor=tutor)
            if lesson is not None
            else {}
        ),
    }


def _target_student_name(db: Session, student_id: str | None) -> str:
    if not student_id:
        return ""
    student = db.get(Student, student_id)
    return student_full_name(student) if student else ""


def _target_group_name(db: Session, group_id: str | None) -> str:
    if not group_id:
        return ""
    group = db.get(Group, group_id)
    return group.name if group else ""
