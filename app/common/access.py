"""Доступ по сессии репетитора: `require_tutor_id` и `LoginRequired`.

Общий код (правило AGENTS.md «общий код — в `common/`»): доступ по сессии
переиспользуется разными доменами (student, calendar и др.), поэтому живёт
здесь, а не внутри модуля student, — новый модуль не получает зависимость
на student. Все вьюхи получают `tutor_id` только отсюда — никогда из формы
или query-параметра. Отсутствие сессии прерывает запрос редиректом на вход.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.tutor.services.sessions import SessionService

LOGIN_URL = "/tutor/login"

_sessions = SessionService()


class LoginRequired(HTTPException):
    """Нет действующей сессии: запрос прерывается редиректом на вход."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": LOGIN_URL},
        )


def require_tutor_id(
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    """FastAPI-зависимость: `tutor_id` вошедшего репетитора либо редирект."""
    tutor_id = _sessions.get_tutor_id_from_request(db, request)
    if tutor_id is None:
        raise LoginRequired()
    return tutor_id


def get_owned_entity(db: Session, model: type, entity_id: str, tutor_id: str):
    """Строка `model` с колонкой `tutor_id`, принадлежащая репетитору, либо 404.

    Единая реализация правила «одна запись одним SELECT»: `id` и `tutor_id`
    проверяются одним запросом, чужая и несуществующая запись неразличимы —
    404, а не 403 и не пустая страница: существование чужой записи не
    раскрывается. Доменные `get_owned_<entity>` делегируют сюда и остаются
    публичным API модулей (типизация, docstring, ри-экспорт);

    Для записей без собственной колонки `tutor_id` (владелец выводится из
    цели — урок, бронь, операция счёта) правило то же, но запрос с JOIN:
    такие выборки живут в своих доменных `services/access.py`.
    """
    entity = db.scalars(
        select(model).where(model.id == entity_id, model.tutor_id == tutor_id)
    ).one_or_none()
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return entity
