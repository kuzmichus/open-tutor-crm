"""Серверные сессии входа репетитора.

Сессия хранится в БД (`tutor_sessions`), клиенту выдаётся token в
httpOnly-cookie. Отзыв = удаление строки, поэтому logout закрывает кабинет
гарантированно (в отличие от подписанных cookie без серверного состояния).
"""

import secrets
from datetime import timedelta

from fastapi import Request
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.tutor.models.tutor_session import TutorSession
from app.tutor.services.clock import as_utc, utcnow

TOKEN_BYTES = 32
TTL = timedelta(days=7)

# Имя httpOnly-cookie, в которой клиенту передаётся токен сессии.
COOKIE_NAME = "tutor_session"


class SessionService:
    """Создание, проверка и удаление сессий репетитора."""

    def create(self, db: Session, tutor_id: str) -> str:
        """Создаёт сессию и возвращает токен для cookie."""
        session = TutorSession(
            tutor_id=tutor_id,
            token=secrets.token_urlsafe(TOKEN_BYTES),
            expires_at=utcnow() + TTL,
        )
        db.add(session)
        db.commit()
        return session.token

    def get_tutor_id(self, db: Session, token: str | None) -> str | None:
        """id репетитора по живой сессии; иначе None (нет входа)."""
        if not token:
            return None
        row = db.scalars(
            select(TutorSession).where(TutorSession.token == token)
        ).one_or_none()
        if row is None:
            return None
        if as_utc(row.expires_at) <= utcnow():
            return None
        return row.tutor_id

    def delete(self, db: Session, token: str | None) -> None:
        """Удаляет сессию (logout); несуществующий токен — no-op."""
        if not token:
            return
        db.execute(delete(TutorSession).where(TutorSession.token == token))
        db.commit()

    def get_tutor_id_from_request(self, db: Session, request: Request) -> str | None:
        """id репетитора по cookie текущего запроса; None — нет живой сессии."""
        return self.get_tutor_id(db, request.cookies.get(COOKIE_NAME))


def set_session_cookie(response: Response, token: str) -> None:
    """Выставляет httpOnly-cookie с токеном сессии.

    `samesite="lax"` снижает риск CSRF; `secure=False` — локальная разработка
    по HTTP (см. design.md, D2).
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Удаляет cookie сессии (logout)."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
