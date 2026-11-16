"""«Уроки» кабинета родителя: недельная сетка занятий всех детей.

Зеркало `calendar.py` кабинета ученика (design D3 change'а
parent-cabinet-unified-pages): тот же каркас `week_bounds`/`now_local`/
`build_calendar_context`, но выборка ведётся по всем ученикам, привязанным
к контакту, — ось карточки «который из детей», а не «который урок».

Выборка — два SELECT (`Lesson.student_id.in_(дети)` и групповые через
`GroupMember.student_id.in_(дети)`) в окне недели по `starts_at`, БЕЗ
фильтра по статусу: прошедшие нужны, чтобы показать их серым. Ребёнок в
архиве учится наравне с активными — фильтра по статусу ученика тоже нет
(спека parent-cabinet, «Дети в архиве»).

Карточка: подпись «Имя ребёнка» или «Имя · Группа», цвет — всегда цвет
ребёнка (`Student.color`), даже у группового урока: родитель ищет в сетке
своего ребёнка, а не группу. Если двое детей в одной группе, у урока две
карточки рядом — по одной на ребёнка, как два пересекающихся занятия:
раскладка пересечений общего календаря это уже умеет.

Оценка берётся из уже выбранных строк (`Lesson.rating` у сущности) —
дополнительного запроса нет; «★ N» рендерит партиал для прошедших
уроков. ДЗ добирается тем же массовым `homework_by_lesson` на всю неделю.

Время — в зоне первого ребёнка (`display_zone_owner`): окно недели,
«сейчас», колонки дней и бейдж пояса считаются в ней; пустой или
неизвестный пояс у ребёнка — зона педагога (решение владельца: родитель
видит то же настенное время, что и его ребёнок).
"""

from dataclasses import replace
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.calendar.services.presentation import build_calendar_context, clock_to_minutes
from app.calendar.services.schedule_day import ScheduleDay
from app.calendar.services.schedule_event import ScheduleEvent
from app.calendar.services.week import week_bounds
from app.calendar.services.week_lesson import WeekLesson
from app.cabinet.services.calendar import PAST_COLOR, homework_by_lesson
from app.cabinet.services.presentation import homework_status_label
from app.common.colors import DEFAULT_TARGET_COLOR
from app.common.services.tutor_time import now_local, tutor_zone_name
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.tutor.services.clock import utcnow
from app.tutor.services.settings import get_settings

# Порог «ближайшего занятия»: только запланированные уроки, ещё не
# начавшиеся по времени (тот же состав, что у `upcoming_lessons`).
NEAREST_STATUS = "planned"


def _full_name(first_name: str | None, last_name: str | None) -> str:
    """«Аня Смирнова» — подпись карточки одной строкой."""
    return " ".join(part for part in (first_name or "", last_name or "") if part)


def display_zone_owner(children: list[Student], tutor):
    """Носитель зоны отображения кабинета родителя (решение владельца).

    Пояс берётся как у ученика: у первого ребёнка в порядке навигации
    (`children()` сортирует по имени) — его часовой пояс с карточки
    (`Student.timezone`). Пустое или неизвестное имя — зона педагога, как
    в напоминаниях ученику (`_student_zone`), а не системная зона сервера:
    родитель видит то же настенное время, что и его ребёнок. У контакта
    без детей — педагог.

    Хелперы `tutor_time` принимают любой объект с атрибутом `.timezone`,
    поэтому возвращается сам ребёнок или карточка педагога.
    """
    if children:
        first = children[0]
        try:
            ZoneInfo(first.timezone or "")
            return first
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            pass  # пустое или неизвестное имя — зона педагога
    return tutor


def parent_week_lessons(
    db: Session, children: list[Student], monday: date, zone_owner
) -> list[WeekLesson]:
    """Уроки недели `monday` по всем детям, индивидуальные и групповые.

    `children` — ученики, привязанные к контакту (активные и архивные):
    список id превращается в `IN` двух выборок. `zone_owner` задаёт зону
    отображения — окно недели считается в настенном времени этой зоны
    (`week_bounds`); у кабинета родителя это первый ребёнок или педагог
    (`display_zone_owner`).

    Подпись и цвет цели: у индивидуального урока — имя ребёнка, у
    группового — «Имя · Группа»; цвет в обоих случаях цвет ребёнка,
    потому что для родителя урок опознаётся по ребёнку (design D3).
    """
    child_ids = [child.id for child in children]
    if not child_ids:
        return []
    start, end = week_bounds(monday, zone_owner)
    rows: list[WeekLesson] = []

    for lesson, first_name, last_name, color in db.execute(
        select(Lesson, Student.first_name, Student.last_name, Student.color)
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Lesson.student_id.in_(child_ids),
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
    ).all():
        rows.append(
            WeekLesson(
                lesson=lesson,
                target_name=_full_name(first_name, last_name),
                target_id=lesson.student_id or "",
                target_color=color or DEFAULT_TARGET_COLOR,
            )
        )

    for lesson, first_name, last_name, color, group_name in db.execute(
        select(
            Lesson,
            Student.first_name,
            Student.last_name,
            Student.color,
            Group.name,
        )
        .join(Group, Group.id == Lesson.group_id)
        .join(GroupMember, GroupMember.group_id == Lesson.group_id)
        .join(Student, Student.id == GroupMember.student_id)
        .where(
            GroupMember.student_id.in_(child_ids),
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
    ).all():
        name = _full_name(first_name, last_name)
        rows.append(
            WeekLesson(
                lesson=lesson,
                # Название группы после имени ребёнка: родитель опознаёт
                # урок по ребёнку, группа — уточнение (design D3).
                target_name=f"{name} · {group_name}" if group_name else name,
                target_id=lesson.student_id or "",
                target_color=color or DEFAULT_TARGET_COLOR,
            )
        )

    rows.sort(key=lambda row: (row.lesson.starts_at, row.lesson.id))
    return rows


def nearest_lesson(
    db: Session, children: list[Student], tutor
) -> tuple[Lesson | None, str]:
    """Ближайшее запланированное занятие среди всех детей и чьё оно.

    Возвращает `(урок, имена детей)`: у индивидуального урока имя одного
    ребёнка, у группового — имена всех детей контакта в этом занятии
    («Аня, Боря»), чтобы плашка отвечала и на «когда», и на «кого».
    Уроков нет или детей нет — `(None, "")`.
    """
    child_ids = [child.id for child in children]
    if not child_ids:
        return None, ""
    now = utcnow()

    # Уроки с именами детей: индивидуальные — цель ребёнок, групповые —
    # строки по членству (двое детей в одной группе дают две строки).
    rows: list[tuple[Lesson, str]] = []
    individual = db.execute(
        select(Lesson, Student.first_name, Student.last_name)
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Lesson.student_id.in_(child_ids),
            Lesson.status == NEAREST_STATUS,
            Lesson.starts_at >= now,
        )
    ).all()
    rows += [
        (lesson, _full_name(first_name, last_name))
        for lesson, first_name, last_name in individual
    ]
    grouped = db.execute(
        select(Lesson, Student.first_name, Student.last_name)
        .join(GroupMember, GroupMember.group_id == Lesson.group_id)
        .join(Student, Student.id == GroupMember.student_id)
        .where(
            GroupMember.student_id.in_(child_ids),
            Lesson.status == NEAREST_STATUS,
            Lesson.starts_at >= now,
        )
    ).all()
    rows += [
        (lesson, _full_name(first_name, last_name))
        for lesson, first_name, last_name in grouped
    ]

    # Один урок — одна карточка ближайшего занятия: имена детей одной
    # группы собираются в одну строку, а не дублируют карточку.
    names_by_lesson: dict[str, list[str]] = {}
    lessons_by_id: dict[str, Lesson] = {}
    for lesson, who in rows:
        lessons_by_id.setdefault(lesson.id, lesson)
        names = names_by_lesson.setdefault(lesson.id, [])
        if who not in names:
            names.append(who)

    ordered = sorted(
        lessons_by_id.values(), key=lambda lesson: (lesson.starts_at, lesson.id)
    )
    if not ordered:
        return None, ""
    nearest = ordered[0]
    # Имена в алфавитном порядке: порядок строк JOIN не гарантирует ничего.
    return nearest, ", ".join(sorted(names_by_lesson[nearest.id]))


def parent_calendar_context(
    db: Session, children: list[Student], tutor, monday: date
) -> dict:
    """Контекст шаблона недельной сетки родителя.

    Собирается тем же кодом, что у ученического календаря
    (`build_calendar_context`): шапка дней, часы, раскладка пересечений
    совпадают с календарём репетитора. Отличия — как у ученического:

    * прошедшие и проведённые уроки всегда серые (`PAST_COLOR`);
    * цена урока не показывается: `price=0` убирает «1 200 ₽» из подписи;
    * отметки недоступности репетитора не передаются — внутренняя
      информация педагога;
    * в каждое представление карточки добавляются `homework_status`,
      `homework_label` и `rating_label` («★ N» оценённого урока).

    Зона отображения — первого ребёнка (`display_zone_owner`): окно
    недели, «сейчас», колонки дней и бейдж пояса считаются в ней; без
    пояса у ребёнка — зона педагога. Рабочие границы сетки — по-прежнему
    настройки педагога (`get_settings` по его id): вид совпадает с
    календарём педагога по часам, а не по зоне.
    """
    settings = get_settings(db, tutor.id)
    grid_start_min = clock_to_minutes(settings.workday_start)
    grid_end_min = clock_to_minutes(settings.workday_end)

    zone_owner = display_zone_owner(children, tutor)

    # «Сейчас» — в зоне отображения: неделя и подсветка текущего дня
    # совпадают с тем, что ребёнок видит в своём кабинете.
    now = now_local(zone_owner)

    rows = parent_week_lessons(db, children, monday, zone_owner)
    homework = homework_by_lesson(db, [row.lesson.id for row in rows])
    # Оценки всех уроков недели одним словарём из уже выбранных строк:
    # звёздочка карточки берётся отсюда, без второго запроса.
    rating_by_lesson = {row.lesson.id: row.lesson.rating for row in rows}

    events_by_day: dict[date, list[ScheduleEvent]] = {}
    past_ids: set[str] = set()
    for row in rows:
        event = ScheduleEvent.from_lesson(
            row.lesson,
            target_name=row.target_name,
            target_id=row.target_id,
            target_color=row.target_color,
            tutor=zone_owner,
        )
        # Проведённый урок — прошедший независимо от часов: репетитор мог
        # отметить его заранее. Остальные гаснут, когда время прошло.
        if row.lesson.status == "completed" or event.starts_at < now:
            past_ids.add(row.lesson.id)
            event = replace(event, color=PAST_COLOR)
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
        tutor=zone_owner,
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
            # Оценка ставится только проведённому уроку, поэтому звёздочка
            # возможна лишь на серой карточке — «★ N» поверх серого читается
            # благодаря отдельному золотому токену (design D3).
            rating = rating_by_lesson.get(lesson_id)
            event_view["rating_label"] = (
                f"★ {rating}" if rating is not None else ""
            )
            if lesson_id in past_ids:
                event_view["is_past"] = True
                event_view["is_overdue"] = False

    # Бейдж часового пояса: время сетки показано в зоне отображения.
    context["timezone_label"] = tutor_zone_name(zone_owner)
    return context
