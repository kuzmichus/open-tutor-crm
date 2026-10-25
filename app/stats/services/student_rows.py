"""Строки вкладки «Ученики» и классификация активности всего модуля статистики.

Классификация — единый критерий для карточек «Обзора» и таблицы вкладки, поэтому
живёт здесь, а не в вьюхах. «Занимался» — есть проведённое **обычное** занятие
(индивидуальное или групповое с участием ученика): пробные не считаются нигде,
иначе ученик с единственным пробным превращался бы в «отвалившегося» (design D2).

Состояния:
- «Активен» — обычное занятие за последние `RECENT_DAYS` дней;
- «Отвалился» (риск потери) — занимался, статус не «В архиве», последнее занятие
  больше `RECENT_DAYS` дней назад и впереди ничего не запланировано;
- «Ушёл» — занимался, а уход отмечен статусом «В архиве»;
- без состояния — не занимался или занимался давно, но что-то запланировано.

Баланс, следующий урок и последняя цена не дублируются: они берутся из
`student.services.list_metrics` (design D5) — правила денег в проекте одни.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.student.services.list_metrics import attach_metrics
from app.tutor.services.clock import as_utc

# Окно «Активен»/«Отвалился» в днях (референс: «занятие за последние 14 дней»).
RECENT_DAYS = 14

# Окно среднего «Занятий/нед»: счётчик за 4 недели, делится на `RATE_WEEKS`.
RATE_WEEKS = 4

# Строк на странице вкладки «Ученики».
PAGE_SIZE = 25

# Значения фильтра состояния активности (пустое — «все ученики»).
ACTIVITY_OPTIONS = ("active", "risk", "lost")
ACTIVITY_LABELS = {
    "active": "Активен",
    "risk": "Отвалился",
    "lost": "Ушёл",
}

# Значения фильтра статуса карточки; пустое — все статусы.
STATUS_OPTIONS = ("new", "active", "archived")


def _tutor_students(db: Session, tutor_id: str) -> list[Student]:
    """Все ученики репетитора, включая архивные.

    Итоговый порядок задаёт `collect_rows` (по дате последнего занятия), здесь
    сортировка — лишь детерминированный базовый порядок, как в списке учеников.
    """
    return list(
        db.scalars(
            select(Student)
            .where(Student.tutor_id == tutor_id)
            .order_by(func.coalesce(Student.last_name, Student.first_name), Student.first_name)
        ).all()
    )


def _last_regular_lessons(db: Session, tutor_id: str) -> dict[str, datetime]:
    """Момент последнего проведённого обычного занятия каждого ученика (UTC).

    Индивидуальные и групповые (через состав групп) в одной куче: для ученика
    «последнее занятие» не зависит от формата. Пустой словарь — никто не занимался.
    """
    result: dict[str, datetime] = {}

    individual = db.execute(
        select(Lesson.student_id, func.max(Lesson.starts_at))
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Student.tutor_id == tutor_id,
            Lesson.status == "completed",
            Lesson.type != "trial",
        )
        .group_by(Lesson.student_id)
    ).all()
    for student_id, starts_at in individual:
        result[student_id] = as_utc(starts_at)

    grouped = db.execute(
        select(GroupMember.student_id, func.max(Lesson.starts_at))
        .join(Lesson, Lesson.group_id == GroupMember.group_id)
        .join(Student, Student.id == GroupMember.student_id)
        .where(
            Student.tutor_id == tutor_id,
            Lesson.status == "completed",
            Lesson.type != "trial",
        )
        .group_by(GroupMember.student_id)
    ).all()
    for student_id, starts_at in grouped:
        current = result.get(student_id)
        value = as_utc(starts_at)
        if current is None or value > current:
            result[student_id] = value
    return result


def _regular_counts_since(
    db: Session, tutor_id: str, since: datetime
) -> dict[str, int]:
    """Число проведённых обычных занятий с `since`: база «Занятий/нед»."""
    counts: dict[str, int] = {}

    individual = db.execute(
        select(Lesson.student_id, func.count())
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Student.tutor_id == tutor_id,
            Lesson.status == "completed",
            Lesson.type != "trial",
            Lesson.starts_at >= since,
        )
        .group_by(Lesson.student_id)
    ).all()
    for student_id, count in individual:
        counts[student_id] = int(count)

    grouped = db.execute(
        select(GroupMember.student_id, func.count())
        .join(Lesson, Lesson.group_id == GroupMember.group_id)
        .join(Student, Student.id == GroupMember.student_id)
        .where(
            Student.tutor_id == tutor_id,
            Lesson.status == "completed",
            Lesson.type != "trial",
            Lesson.starts_at >= since,
        )
        .group_by(GroupMember.student_id)
    ).all()
    for student_id, count in grouped:
        counts[student_id] = counts.get(student_id, 0) + int(count)
    return counts


def _students_with_future(db: Session, tutor_id: str, now: datetime) -> set[str]:
    """Ученики, у которых есть запланированное занятие (любого типа) с `now`.

    Будущие пробные тоже считаются: назначенное занятие любого вида означает,
    что ученик «на связи», и риском потери он не является.
    """
    found: set[str] = set()

    individual = db.scalars(
        select(Lesson.student_id)
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Student.tutor_id == tutor_id,
            Lesson.status == "planned",
            Lesson.starts_at >= now,
        )
        .distinct()
    ).all()
    found.update(individual)

    grouped = db.scalars(
        select(GroupMember.student_id)
        .join(Lesson, Lesson.group_id == GroupMember.group_id)
        .join(Student, Student.id == GroupMember.student_id)
        .where(
            Student.tutor_id == tutor_id,
            Lesson.status == "planned",
            Lesson.starts_at >= now,
        )
        .distinct()
    ).all()
    found.update(grouped)
    return found


def classify(
    *,
    status: str,
    last_at: datetime | None,
    has_future: bool,
    now: datetime,
) -> str | None:
    """Состояние активности ученика; состояния нет — `None` («—» в таблице).

    Чистая функция без БД: на вход — уже собранные признаки. Порядок проверок
    важен: «Ушёл» сильнее «Отвалившегося» — архивный ученик без занятий
    давно — осознанный уход, а не риск.
    """
    if last_at is None:
        return None  # не занимался — ни активен, ни потерян
    if status == "archived":
        return "lost"
    if last_at >= now - timedelta(days=RECENT_DAYS):
        return "active"
    if not has_future:
        return "risk"
    return None


def collect_rows(db: Session, tutor, *, now: datetime) -> list[dict]:
    """Строки всех учеников репетитора с метриками и состоянием активности.

    Один набор агрегатов на страницу (как в `list_metrics`): запросов на
    ученика нет. Строка содержит ORM-ученика и готовые признаки — шаблон
    ничего не считает сам.
    """
    students = _tutor_students(db, tutor.id)
    student_ids = [student.id for student in students]
    last_map = _last_regular_lessons(db, tutor.id)
    counts = _regular_counts_since(
        db, tutor.id, now - timedelta(days=RATE_WEEKS * 7)
    )
    with_future = _students_with_future(db, tutor.id, now)

    # `attach_metrics` читает только `card["student"].id`: минимальные
    # карточки без контактов — контакты статистике не нужны.
    cards = attach_metrics(db, [{"student": s} for s in students], now=now)

    rows = []
    for card in cards:
        student = card["student"]
        last_at = last_map.get(student.id)
        rows.append(
            {
                "student": student,
                "balance": card["balance"],
                "last_price": card["last_price"],
                "next_at": card["next_lesson_at"],
                "last_lesson_at": last_at,
                "week_count": counts.get(student.id, 0),
                "has_future": student.id in with_future,
                "activity": classify(
                    status=student.status,
                    last_at=last_at,
                    has_future=student.id in with_future,
                    now=now,
                ),
            }
        )

    # Референс: списки отсортированы по дате последнего занятия; никогда не
    # занимавшие уходят в конец, внутри групп — по имени.
    rows.sort(
        key=lambda row: (
            row["last_lesson_at"] is None,
            -(row["last_lesson_at"].timestamp() if row["last_lesson_at"] else 0),
            row["student"].first_name,
            row["student"].last_name or "",
        )
    )
    return rows


def _matches_q(student: Student, needle: str) -> bool:
    """Поиск по ФИО без учёта регистра, включая кириллицу (как в списке учеников).

    SQLite `lower()` работает только с ASCII, поэтому сравнение в Python:
    карточек у репетитора немного, а поведение одинаково на любой локали.
    """
    haystack = " ".join(
        part for part in (student.first_name, student.last_name) if part
    )
    return needle in haystack.casefold()


def apply_filters(
    rows: list[dict],
    *,
    q: str = "",
    status: str = "",
    activity: str = "",
    no_future: bool = False,
) -> list[dict]:
    """Фильтрация строк вкладки; неизвестные значения фильтров игнорируются."""
    needle = q.strip().casefold()
    result = rows
    if needle:
        result = [row for row in result if _matches_q(row["student"], needle)]
    if status in STATUS_OPTIONS:
        result = [row for row in result if row["student"].status == status]
    if activity in ACTIVITY_OPTIONS:
        result = [row for row in result if row["activity"] == activity]
    if no_future:
        # «Без будущих занятий» — не ушедшие ученики без запланированных:
        # ушедших и так видно фильтром «Ушёл», смешивать не нужно.
        result = [
            row
            for row in result
            if row["activity"] != "lost" and not row["has_future"]
        ]
    return result


def paginate(rows: list[dict], page_raw: str) -> tuple[list[dict], dict]:
    """Срез страницы и метки пагинации; мусорный номер страницы — первая."""
    total = len(rows)
    pages = max(1, -(-total // PAGE_SIZE))
    try:
        page = int(page_raw)
    except (TypeError, ValueError):
        page = 1
    page = min(max(page, 1), pages)
    start = (page - 1) * PAGE_SIZE
    return (
        rows[start : start + PAGE_SIZE],
        {"page": page, "pages": pages, "total": total},
    )
