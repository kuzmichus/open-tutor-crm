"""Доступ к задаче: `get_owned_task` по колонке `tutor_id`.

У задачи, в отличие от урока и брони, есть собственная колонка `tutor_id`:
ответственного исполнителя нет, задача ставится себе, поэтому владелец
выводится прямо из строки. Проверка — общий `get_owned_entity`: `id` и
`tutor_id` в одном `SELECT`, чужая и несуществующая задача неразличимы
(404, а не 403).

Ри-экспорт `require_tutor_id`/`LoginRequired` — по правилу AGENTS.md:
вьюхи модуля не зависят от `common` напрямую.
"""

from sqlalchemy.orm import Session

from app.common.access import LOGIN_URL, LoginRequired, get_owned_entity
from app.common.access import require_tutor_id
from app.task.models.task import Task

__all__ = ["LOGIN_URL", "LoginRequired", "get_owned_task", "require_tutor_id"]


def get_owned_task(db: Session, task_id: str, tutor_id: str) -> Task:
    """Задача этого репетитора либо 404."""
    return get_owned_entity(db, Task, task_id, tutor_id)
