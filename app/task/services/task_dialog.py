"""Контекст диалога задачи (`task/_dialog.html`).

Один шаблон на три случая: создание, правка и повторный показ с ошибками.
При ошибке присланные значения перекрывают умолчания (паттерн
`expense_dialog_context`): ошибка в названии не должна затирать
выбранные срок, этап и учеников.

Сервис не знает про FastAPI: на вход — репетитор, `Session` и значения
формы, на выход — контекст шаблона. Варианты учеников отдаются сразу
готовым JSON для `data-options` общего виджета `createPersonPicker`.
"""

from json import dumps

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.student.models.student import Student
from app.student.services.presentation import student_full_name
from app.task.models.task import (
    TASK_PRIORITIES,
    TASK_PRIORITY_LABELS,
    TASK_STAGES,
    TASK_STAGE_LABELS,
    Task,
)
from app.task.models.task_student import TaskStudent
from app.task.services.student_options import student_options


def task_student_ids(db: Session, task: Task) -> list[str]:
    """Id учеников, привязанных к задаче (порядок — по имени ученика)."""
    return list(
        db.scalars(
            select(TaskStudent.student_id)
            .join(Student, Student.id == TaskStudent.student_id)
            .where(TaskStudent.task_id == task.id)
            .order_by(Student.first_name, Student.last_name, Student.id)
        ).all()
    )


def empty_task_form() -> dict:
    """Пустая форма задачи: этап «Новые», приоритет «Средний», без срока.

    Дат по умолчанию нет: «Без срока» — законное состояние, и
    подставлять сегодняшний день значило бы придумывать срок за педагога.
    """
    return {
        "title": "",
        "priority": "medium",
        "stage": "new",
        "due_value": "",
        "description": "",
    }


def task_dialog_context(
    db: Session,
    tutor,
    *,
    task: Task | None = None,
    data: dict | None = None,
    errors: list[str] | None = None,
) -> dict:
    """Контекст диалога: значения полей, варианты, ошибки, ученики задачи.

    `data` — очищенные значения формы при ошибке; `task` — правимая
    задача (у неё заполняются ученики и заголовок диалога).
    """
    values = empty_task_form()
    if data is not None:
        values = {
            "title": data.get("title") or "",
            "priority": data.get("priority") or "medium",
            "stage": data.get("stage") or "new",
            "due_value": (
                data["due_date"].strftime("%Y-%m-%d")
                if data.get("due_date")
                else ""
            ),
            "description": data.get("description") or "",
        }
    elif task is not None:
        values = {
            "title": task.title,
            "priority": task.priority,
            "stage": task.stage,
            "due_value": (
                task.due_date.strftime("%Y-%m-%d") if task.due_date else ""
            ),
            "description": task.description or "",
        }

    if data is not None:
        selected_ids = list(data.get("student_ids") or [])
    elif task is not None:
        selected_ids = task_student_ids(db, task)
    else:
        selected_ids = []

    # Уже выбранных учеников из общего списка исключаем: повторный выбор
    # в поле создал бы дубль строки, а сервер отклонил бы форму.
    options = [
        option
        for option in student_options(db, tutor.id)
        if option["id"] not in selected_ids
    ]

    return {
        "task": task,
        "task_form": values,
        "task_errors": errors or [],
        "task_priorities": TASK_PRIORITIES,
        "task_priority_labels": TASK_PRIORITY_LABELS,
        "task_stages": TASK_STAGES,
        "task_stage_labels": TASK_STAGE_LABELS,
        "task_selected": _selected_rows(db, tutor, selected_ids),
        "task_options_json": dumps(options, ensure_ascii=False, separators=(",", ":")),
    }


def _selected_rows(db: Session, tutor, selected_ids: list[str]) -> list[dict]:
    """Имена выбранных учеников для стартового состояния формы.

    Имена берутся из БД, а не из формы: при ошибке валидации клиент
    должен показать те же строки, что и до отправки.
    """
    if not selected_ids:
        return []
    rows = db.scalars(
        select(Student)
        .where(Student.id.in_(selected_ids), Student.tutor_id == tutor.id)
        .order_by(Student.first_name, Student.last_name, Student.id)
    ).all()
    return [
        {"id": student.id, "name": student_full_name(student)}
        for student in rows
    ]
