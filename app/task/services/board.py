"""Доска и список задач: выборка, группировка и подписи для шаблона.

Два вида страницы собираются одним сервисом из одной выборки:

- **доска** — четыре колонки по этапам (`TASK_STAGES`), внутри колонки
  задачи по сроку: ближайшие сверху, без срока — в конце;
- **список** — блоки «Сегодня», «Предстоящие», «Без срока», «Завершено».
  «Сегодня» собирает срок сегодня и просроченные: просроченная задача —
  это работа на сегодня, прятать её в «Предстоящие» значило бы врать.
  «Завершено» — задачи этапа «Готово», последняя завершённая сверху.

Ученики каждой задачи подгружаются одним запросом с `join` и группируются
в Python (связи объявлены только FK-колонками, N+1 на карточку не нужен).

Сервис не знает про FastAPI: на вход — `Session`, `tutor_id`, карточка
педагога и сегодняшняя дата в его зоне; на выход — контекст шаблона.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.student.models.student import Student
from app.student.services.presentation import student_full_name
from app.task.models.task import (
    TASK_DONE_STAGE,
    TASK_STAGES,
    Task,
)
from app.task.models.task_student import TaskStudent
from app.task.services.presentation import (
    due_label,
    priority_label,
    stage_label,
)
from app.tutor.services.clock import as_utc

# Виды страницы: доска по этапам и список по срокам.
TASK_VIEWS = ("board", "list")


def normalize_view(value: str) -> str:
    """Значение вида из query; неизвестное — «доска» (умолчание)."""
    return value if value in TASK_VIEWS else "board"


def _students_by_task(db: Session, task_ids: list[str]) -> dict[str, list[dict]]:
    """Ученики задач одним запросом: `{task_id: [{id, name}, ...]}`."""
    if not task_ids:
        return {}
    rows = db.execute(
        select(TaskStudent.task_id, Student)
        .join(Student, Student.id == TaskStudent.student_id)
        .where(TaskStudent.task_id.in_(task_ids))
        .order_by(Student.first_name, Student.last_name, Student.id)
    ).all()
    grouped: dict[str, list[dict]] = {}
    for task_id, student in rows:
        grouped.setdefault(task_id, []).append(
            {"id": student.id, "name": student_full_name(student)}
        )
    return grouped


def _row(task: Task, students: list[dict], *, today: date) -> dict:
    """Карточка/строка задачи: объект, ученики и готовые подписи."""
    return {
        "task": task,
        "students": students,
        "student_names": ", ".join(item["name"] for item in students),
        "stage_label": stage_label(task.stage),
        "priority_label": priority_label(task.priority),
        "due": due_label(task.due_date, today),
        # Просрочена — срок раньше сегодняшнего дня и задача не завершена.
        "overdue": bool(
            task.due_date
            and task.due_date < today
            and task.stage != TASK_DONE_STAGE
        ),
    }


def _sort_by_due(rows: list[dict]) -> list[dict]:
    """Срок ближайший сверху; задачи без срока — в конце.

    Второй ключ — момент создания: внутри одного срока порядок стабилен
    и не зависит от порядка строк в БД.
    """
    return sorted(
        rows,
        key=lambda row: (
            row["task"].due_date is None,
            row["task"].due_date or date.max,
            as_utc(row["task"].created_at),
        ),
    )


def task_rows(
    db: Session,
    tutor_id: str,
    *,
    today: date,
    student_id: str = "",
) -> list[dict]:
    """Все задачи репетитора карточками; `student_id` — фильтр по ученику."""
    stmt = select(Task).where(Task.tutor_id == tutor_id)
    if student_id:
        # Фильтр по ученику — JOIN, а не выборка id в Python: чужой
        # student_id просто ничего не найдёт, изоляция не страдает.
        stmt = stmt.join(TaskStudent, TaskStudent.task_id == Task.id).where(
            TaskStudent.student_id == student_id
        )
    tasks = list(db.scalars(stmt).all())
    students = _students_by_task(db, [task.id for task in tasks])
    return [_row(task, students.get(task.id, []), today=today) for task in tasks]


def overdue_count(db: Session, tutor_id: str, *, today: date) -> int:
    """Число просроченных задач — счётчик в сайдбаре (пункт «Задачи»).

    То же правило просрочки, что у метки карточки в `_row`: срок раньше
    сегодняшнего дня и этап не «Готово». Агрегат на сервере, а не
    `len(rows)`: счётчику не нужны карточки и подписи списка.
    """
    return (
        db.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.tutor_id == tutor_id,
                Task.stage != TASK_DONE_STAGE,
                Task.due_date.is_not(None),
                Task.due_date < today,
            )
        )
        or 0
    )


def board_columns(rows: list[dict]) -> list[dict]:
    """Колонки доски: этап, подпись и задачи в порядке срока."""
    columns: list[dict] = []
    for stage in TASK_STAGES:
        if stage == TASK_DONE_STAGE:
            # Завершённые — последняя завершённая сверху: блок читается
            # как хроника, а не как список старых дел.
            items = sorted(
                (row for row in rows if row["task"].stage == stage),
                key=lambda row: as_utc(
                    row["task"].completed_at or row["task"].updated_at
                ),
                reverse=True,
            )
        else:
            items = _sort_by_due(
                [row for row in rows if row["task"].stage == stage]
            )
        columns.append(
            {
                "stage": stage,
                "label": stage_label(stage),
                "rows": items,
                "count": len(items),
            }
        )
    return columns


def list_groups(rows: list[dict], *, today: date) -> list[dict]:
    """Блоки списка: «Сегодня», «Предстоящие», «Без срока», «Завершено».

    «Без срока» показывается только когда в нём что-то есть: пустой блок
    в интерфейсе ничего не объясняет.
    """
    open_rows = [row for row in rows if row["task"].stage != TASK_DONE_STAGE]
    done_rows = sorted(
        (row for row in rows if row["task"].stage == TASK_DONE_STAGE),
        key=lambda row: as_utc(
            row["task"].completed_at or row["task"].updated_at
        ),
        reverse=True,
    )

    today_rows = _sort_by_due(
        [
            row
            for row in open_rows
            if row["task"].due_date and row["task"].due_date <= today
        ]
    )
    upcoming_rows = _sort_by_due(
        [
            row
            for row in open_rows
            if row["task"].due_date and row["task"].due_date > today
        ]
    )
    no_due_rows = _sort_by_due(
        [row for row in open_rows if row["task"].due_date is None]
    )

    groups = [
        {
            "key": "today",
            "label": "Сегодня",
            "rows": today_rows,
            "count": len(today_rows),
            "empty": "На сегодня задач нет.",
        },
        {
            "key": "upcoming",
            "label": "Предстоящие",
            "rows": upcoming_rows,
            "count": len(upcoming_rows),
            "empty": "Список пуст",
        },
    ]
    if no_due_rows:
        groups.append(
            {
                "key": "no_due",
                "label": "Без срока",
                "rows": no_due_rows,
                "count": len(no_due_rows),
                "empty": "Список пуст",
            }
        )
    groups.append(
        {
            "key": "done",
            "label": "Завершено",
            "rows": done_rows,
            "count": len(done_rows),
            "empty": "Завершённых задач нет.",
        }
    )
    return groups


def tasks_context(
    db: Session,
    tutor_id: str,
    *,
    today: date,
    view: str = "board",
    student_id: str = "",
) -> dict:
    """Контекст страницы и партиала: выбранный вид, доска, список, этапы."""
    rows = task_rows(db, tutor_id, today=today, student_id=student_id)
    return {
        "view": normalize_view(view),
        "student_id": student_id,
        "columns": board_columns(rows),
        "groups": list_groups(rows, today=today),
        # Этапы для меню карточки: шаблон не перечисляет закрытый список сам.
        "stage_choices": [
            {"value": stage, "label": stage_label(stage)}
            for stage in TASK_STAGES
        ],
    }
