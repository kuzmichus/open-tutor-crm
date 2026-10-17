"""Одноразовые ключи восстановления пароля репетитора.

Ключ (`tutor_password_reset_tokens`) создаётся по запросу со страницы
восстановления и живёт ограниченное время. Использованный или истёкший
ключ отклоняется; повторная установка пароля по нему невозможна.
"""

import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.tutor.models.password_reset_token import PasswordResetToken
from app.tutor.services.clock import as_utc, utcnow

TOKEN_BYTES = 32
TTL = timedelta(hours=24)


class PasswordResetService:
    """Создание, проверка и погашение ключей восстановления пароля."""

    def create(self, db: Session, tutor_id: str) -> str:
        """Создаёт ключ и возвращает его значение для ссылки."""
        token = PasswordResetToken(
            tutor_id=tutor_id,
            token=secrets.token_urlsafe(TOKEN_BYTES),
            expires_at=utcnow() + TTL,
        )
        db.add(token)
        db.commit()
        return token.token

    def get_tutor_id(self, db: Session, token: str | None) -> str | None:
        """id репетитора по действующему ключу; иначе None.

        Действующий = существует, не использован и не истёк.
        """
        if not token:
            return None
        row = db.scalars(
            select(PasswordResetToken).where(PasswordResetToken.token == token)
        ).one_or_none()
        if row is None:
            return None
        if row.used_at is not None:
            return None
        if as_utc(row.expires_at) <= utcnow():
            return None
        return row.tutor_id

    def consume(self, db: Session, token: str) -> None:
        """Помечает ключ использованным (в одной транзакции со сменой пароля)."""
        db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.token == token)
            .values(used_at=utcnow())
        )
