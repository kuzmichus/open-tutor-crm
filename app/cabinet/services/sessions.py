"""Серверные сессии ученика: БД + httpOnly-cookie `student_session`.

По образцу сессий репетитора (`app/tutor/services/sessions.py`), но со
своей таблицей и своим именем cookie (D4): имена не пересекаются, поэтому
вход и выход ученика не затрагивают сессию репетитора в том же браузере,
и обе сессии работают параллельно. Отзыв = удаление строки: «Выход»
закрывает кабинет гарантированно, как и у репетитора.
"""

import secrets
from datetime import timedelta

from fastapi import Request
from fastapi.responses import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.cabinet.models.session import StudentSession
from app.tutor.services.clock import as_utc, utcnow

TOKEN_BYTES = 32
TTL = timedelta(days=7)

# Имя httpOnly-cookie кабинета; не совпадает с `tutor_session` —
# независимость сессий держится на разных именах (тест 6.2 change'а).
COOKIE_NAME = "student_session"


def create_session(db: Session, student_id: str) -> str:
    """Создаёт сессию ученика и возвращает токен для cookie."""
    row = StudentSession(
        student_id=student_id,
        token=secrets.token_urlsafe(TOKEN_BYTES),
        expires_at=utcnow() + TTL,
    )
    db.add(row)
    db.commit()
    return row.token


def get_student_id(db: Session, token: str | None) -> str | None:
    """id ученика по живой сессии; иначе None (нет входа в кабинет)."""
    if not token:
        return None
    row = db.scalars(
        select(StudentSession).where(StudentSession.token == token)
    ).one_or_none()
    if row is None:
        return None
    if as_utc(row.expires_at) <= utcnow():
        return None
    return row.student_id


def delete_session(db: Session, token: str | None) -> None:
    """Удаляет сессию (выход из кабинета); несуществующий токен — no-op."""
    if not token:
        return
    db.execute(delete(StudentSession).where(StudentSession.token == token))
    db.commit()


def get_student_id_from_request(db: Session, request: Request) -> str | None:
    """id ученика по cookie текущего запроса; None — нет живой сессии."""
    return get_student_id(db, request.cookies.get(COOKIE_NAME))


def set_student_cookie(response: Response, token: str) -> None:
    """Выставляет httpOnly-cookie кабинета.

    `samesite="lax"` — как у сессии репетитора; `secure=False` — локальная
    разработка по HTTP. Cookie кабинета не трогает cookie репетитора:
    имена разные, атрибуты не пересекаются.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=int(TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_student_cookie(response: Response) -> None:
    """Удаляет cookie кабинета (выход)."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
