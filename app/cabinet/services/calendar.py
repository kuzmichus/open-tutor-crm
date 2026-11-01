"""«Мои уроки» кабинета: недельный календарь ученика в режиме только чтения.

Список ближайших занятий заменён сеткой недели (change
student-lessons-calendar): ученик видит свои уроки в той же сетке, что
репетитор в `/tutor/calendar`, но без интерактивности — нельзя переносить,
открывать и редактировать занятие. Поэтому здесь нет ни слотов-целей для
клика, ни `calendar.js`: сервис отдаёт только данные для пассивного
рендера.

Выборка — два SELECT (индивидуальные + групповые через `GroupMember`) в
окне недели по `starts_at`, БЕЗ фильтра по статусу: прошедшие и
проведённые уроки нужны, чтобы показать их серым. Границы окна считаются
в зоне репетитора (`local_week_bounds`) — время в кабинете ученика тоже
показывается в зоне педагога (спека student-cabinet).

ДЗ добирается одним массовым SELECT по id уроков недели (правило
AGENTS.md 9, без N+1 на карточку) и кладётся прямо в представление
карточки: `homework_status`/`homework_label` пустые, если задания нет.
"""

from dataclasses import replace
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.services.homework import HIDDEN_STATUSES
from app.cabinet.services.presentation import homework_status_label
from app.calendar.services.presentation import build_calendar_context, clock_to_minutes
from app.calendar.services.schedule_day import ScheduleDay
from app.calendar.services.schedule_event import ScheduleEvent
from app.calendar.services.week import week_bounds
from app.calendar.services.week_lesson import WeekLesson
from app.common.colors import DEFAULT_TARGET_COLOR
from app.common.services.tutor_time import now_local, tutor_zone_name
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.homework.models.homework import Homework
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.services.settings import get_settings

# Подпись индивидуального урока в карточке: ученику не нужно собственное
# имя, поэтому вместо «Аня А.» стоит просто «Урок» (требование задачи).
LESSON_LABEL = "Урок"

# Акцент прошедшего урока: приглушённый серый токен темы. Ссылка на
# переменную, а не литерал: тёмная тема задаёт значение сама
# (правило «цвета только в @layer tokens»).
PAST_COLOR = "var(--muted-foreground)"


def student_week_lessons(
    db: Session, student_id: str, monday: date, tutor
) -> list[WeekLesson]:
    """Уроки ученика за неделю `monday` — индивидуальные и групповые.

    `tutor` задаёт зону: окно недели считается в настенном времени
    педагога и переводится в UTC (`week_bounds`), потому что `starts_at`
    хранится в UTC (спека tutor-timezone).

    Подпись цели: для группового урока — название группы, для остальных —
    «Урок». Цвет цели берётся из палитры ученика/группы: по нему карточка
    и точка в шапке дня окрашиваются одинаково.
    """
    start, end = week_bounds(monday, tutor)
    rows: list[WeekLesson] = []

    for lesson, color in db.execute(
        select(Lesson, Student.color)
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Lesson.student_id == student_id,
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
    ).all():
        rows.append(
            WeekLesson(
                lesson=lesson,
                target_name=LESSON_LABEL,
                target_id=student_id,
                target_color=color or DEFAULT_TARGET_COLOR,
            )
        )

    for lesson, name, color in db.execute(
        select(Lesson, Group.name, Group.color)
        .join(Group, Group.id == Lesson.group_id)
        .join(GroupMember, GroupMember.group_id == Lesson.group_id)
        .where(
            GroupMember.student_id == student_id,
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
    ).all():
        rows.append(
            WeekLesson(
                lesson=lesson,
                target_name=name or LESSON_LABEL,
                target_id=lesson.group_id or "",
                target_color=color or DEFAULT_TARGET_COLOR,
            )
        )

    rows.sort(key=lambda row: (row.lesson.starts_at, row.lesson.id))
    return rows


def homework_by_lesson(db: Session, lesson_ids: list[str]) -> dict[str, str]:
    """Статусы ДЗ по id уроков: один SELECT на всю неделю.

    «Не задано» (`HIDDEN_STATUSES`) не попадает в карту: пустая запись —
    это отсутствие домашнего задания, значка в карточке быть не должно.
    """
    if not lesson_ids:
        return {}
    rows = db.execute(
        select(Homework.lesson_id, Homework.status).where(
            Homework.lesson_id.in_(lesson_ids),
            Homework.status.not_in(HIDDEN_STATUSES),
        )
    ).all()
    return {lesson_id: status for lesson_id, status in rows}


def student_calendar_context(
    db: Session, student, tutor, monday: date
) -> dict:
    """Контекст шаблона недельного календаря ученика.

    Собирает `ScheduleDay` по семи датам и отдаёт их общему
    `build_calendar_context` — вид сетки (шапка дней, часы, раскладка
    пересечений) считается тем же кодом, что у календаря репетитора.

    Отличия кабинета ученика:

    * цвет карточки — цвет цели (ученика/группы), прошедшие и проведённые
      уроки всегда серые (`PAST_COLOR`);
    * цена урока не показывается: `price=0` убирает её из подписи;
    * отметки недоступности репетитора не передаются (`unavailable=None`) —
      это внутренняя информация педагога;
    * в каждое представление карточки добавляются `homework_status` и
      `homework_label` — значок ДЗ в разметке.

    Границы сетки — рабочее время репетитора: вид совпадает с календарём
    педагога, а урок вне границ по-прежнему виден (зажим `_visible_span`).
    """
    settings = get_settings(db, tutor.id)
    grid_start_min = clock_to_minutes(settings.workday_start)
    grid_end_min = clock_to_minutes(settings.workday_end)

    # «Сейчас» и «сегодня» — в зоне педагога: неделя и подсветка текущего
    # дня должны совпадать с календарём репетитора (design D7 календаря).
    now = now_local(tutor)

    rows = student_week_lessons(db, student.id, monday, tutor)
    homework = homework_by_lesson(db, [row.lesson.id for row in rows])

    events_by_day: dict[date, list[ScheduleEvent]] = {}
    past_ids: set[str] = set()
    for row in rows:
        event = ScheduleEvent.from_lesson(
            row.lesson,
            target_name=row.target_name,
            target_id=row.target_id,
            target_color=row.target_color,
            tutor=tutor,
        )
        # Проведённый урок — прошедший независимо от часов: репетитор мог
        # отметить его заранее. Остальные гаснут, когда время прошло.
        if row.lesson.status == "completed" or event.starts_at < now:
            past_ids.add(row.lesson.id)
            event = replace(event, color=PAST_COLOR)
        # Цена ученику не показывается: пустая цена убирает «1 200 ₽» из
        # подписи карточки (format_price возвращает пустую строку).
        event = replace(event, price=0)
        events_by_day.setdefault(event.day, []).append(event)

    days = [
        ScheduleDay(
            date=monday + timedelta(days=offset),
            events=tuple(events_by_day.get(monday + timedelta(days=offset), ())),
        )
        for offset in range(7)
    ]

    context = build_calendar_context(
        days,
        now=now,
        tutor=tutor,
        grid_start_min=grid_start_min,
        grid_end_min=grid_end_min,
    )

    for day_view in context["days"]:
        for event_view in day_view["lessons"]:
            lesson_id = event_view.get("lesson_id") or ""
            status = homework.get(lesson_id, "")
            event_view["homework_status"] = status
            event_view["homework_label"] = (
                homework_status_label(status) if status else ""
            )
            if lesson_id in past_ids:
                # Проведённый урок в будущем тоже серый — «прошёл» здесь
                # означает «уже не предстоит», а не «время наступило».
                event_view["is_past"] = True
                event_view["is_overdue"] = False

    # Бейдж часового пояса: время сетки показано в зоне педагога.
    context["timezone_label"] = tutor_zone_name(tutor)
    return context
