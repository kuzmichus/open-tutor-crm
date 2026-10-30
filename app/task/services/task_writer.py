"""Запись задач: создание, правка, смена этапа и удаление.

Сервис не знает про FastAPI: на вход — `Session`, `tutor_id` и очищенные
данные формы, на выход — задача или список ошибок. Владелец задачи —
`tutor_id` из сессии; ученики проверяются на принадлежность тому же
репетитору (чужой id в форме — ошибка, а не тихая привязка).

Момент завершения (`completed_at`) держится здесь, а не в шаблоне:
переход в «Готово» ставит дату, возврат из «Готово» её сбрасывает —
иначе «Завершено» показывал бы старые даты у вернувшихся в работу задач.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.student.models.student import Student
from app.task.models.task import TASK_DONE_STAGE, TASK_STAGES, Task
from app.task.models.task_student import TaskStudent
from app.tutor.services.clock import utcnow


def _owned_student_ids(
    db: Session, tutor_id: str, student_ids: list[str]
) -> tuple[list[str], list[str]]:
    """Разделяет присланные id на свои и чужие/несуществующие.

    Один `SELECT` по всем id сразу: проверять каждого ученика отдельным
    запросом значило бы N+1 на каждое сохранение формы.
    """
    if not student_ids:
        return [], []
    owned = set(
        db.scalars(
            select(Student.id).where(
                Student.id.in_(student_ids),
                Student.tutor_id == tutor_id,
            )
        ).all()
    )
    return (
        [student_id for student_id in student_ids if student_id in owned],
        [student_id for student_id in student_ids if student_id not in owned],
    )


def _replace_students(
    db: Session, task: Task, student_ids: list[str]
) -> None:
    """Состав учеников задачи = присланный список (старые связки удаляются)."""
    db.execute(delete(TaskStudent).where(TaskStudent.task_id == task.id))
    for student_id in student_ids:
        db.add(TaskStudent(task_id=task.id, student_id=student_id))


def create_task(
    db: Session, tutor_id: str, data: dict
) -> tuple[Task | None, list[str]]:
    """Создаёт задачу репетитора; возвращает задачу или ошибки."""
    student_ids, foreign = _owned_student_ids(
        db, tutor_id, data.get("student_ids", [])
    )
    if foreign:
        return None, ["Выбранный ученик не найден."]

    task = Task(
        tutor_id=tutor_id,
        title=data["title"],
        stage=data["stage"],
        priority=data["priority"],
        due_date=data.get("due_date"),
        description=data.get("description"),
    )
    if task.stage == TASK_DONE_STAGE:
        task.completed_at = utcnow()

    db.add(task)
    db.flush()  # id задачи нужен связкам учеников до commit
    _replace_students(db, task, student_ids)
    db.commit()
    db.refresh(task)
    return task, []


def update_task(
    db: Session, task: Task, tutor_id: str, data: dict
) -> tuple[Task | None, list[str]]:
    """Сохраняет поля задачи; возвращает задачу или ошибки."""
    student_ids, foreign = _owned_student_ids(
        db, tutor_id, data.get("student_ids", [])
    )
    if foreign:
        return None, ["Выбранный ученик не найден."]

    was_done = task.stage == TASK_DONE_STAGE
    task.title = data["title"]
    task.priority = data["priority"]
    task.due_date = data.get("due_date")
    task.description = data.get("description")

    if data["stage"] != task.stage:
        set_stage(task, data["stage"])
    elif data["stage"] == TASK_DONE_STAGE and not was_done:
        task.completed_at = utcnow()

    _replace_students(db, task, student_ids)
    db.commit()
    db.refresh(task)
    return task, []


def set_stage(task: Task, stage: str) -> None:
    """Переводит задачу на этап, синхронизируя момент завершения.

    Значение этапа проверяется вызывающим: форма уже отсеяла мусор, а
    роут перетаскивания берёт этап из закрытого списка `TASK_STAGES`.
    """
    if stage not in TASK_STAGES:
        raise ValueError(f"неизвестный этап задачи: {stage!r}")
    was_done = task.stage == TASK_DONE_STAGE
    task.stage = stage
    if stage == TASK_DONE_STAGE:
        # Повторный перевод в «Готово» не сдвигает дату завершения:
        # задача завершена тогда, когда это случилось впервые.
        if not was_done or task.completed_at is None:
            task.completed_at = utcnow()
    else:
        task.completed_at = None


def move_task(db: Session, task: Task, stage: str) -> None:
    """Меняет этап задачи (перетаскивание карточки) и сохраняет."""
    set_stage(task, stage)
    db.commit()
    db.refresh(task)


def delete_task(db: Session, task: Task) -> None:
    """Удаляет задачу; связки учеников уходят каскадом."""
    db.delete(task)
    db.commit()


def parse_stage(raw: str) -> str | None:
    """Этап из формы перетаскивания; неизвестное значение — None."""
    return raw if raw in TASK_STAGES else None
