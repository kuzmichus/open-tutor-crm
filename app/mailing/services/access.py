"""Доступ к сущностям рассылок: ри-экспорт общего доступа и шаблоны по владельцу.

Ри-экспорт `require_tutor_id`/`LoginRequired` — по правилу AGENTS.md:
вьюхи модуля не зависят от `common` напрямую.
"""

from sqlalchemy.orm import Session

from app.common.access import LOGIN_URL, LoginRequired, get_owned_entity
from app.common.access import require_tutor_id
from app.mailing.models.message_template import MessageTemplate

__all__ = ["LOGIN_URL", "LoginRequired", "get_owned_template", "require_tutor_id"]


def get_owned_template(
    db: Session, template_id: str, tutor_id: str
) -> MessageTemplate:
    """Шаблон этого репетитора либо 404.

    `id` и `tutor_id` в одном `SELECT`: чужой шаблон и несуществующий
    неразличимы (404, а не 403) — существование чужой записи не
    раскрывается.
    """
    return get_owned_entity(db, MessageTemplate, template_id, tutor_id)
