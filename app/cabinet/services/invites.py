"""Приглашение в личный кабинет: одноразовая ссылка `/invite/<token>`.

Одна строка на ученика: «Создать приглашение» при активной ссылке
обновляет `token` и `expires_at` — прежняя гасится сама (семантика
приглашений в мессенджеры). Рендер блока карточки сетенезависим: читаются
только строки БД, сеть не дёргается (в отличие от приглашений в
мессенджеры, бот здесь не нужен — D8 change'а student-cabinet-access).
"""

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.models.invite import TOKEN_LENGTH, StudentCabinetInvite
from app.student.services.credentials import get_access
from app.tutor.services.clock import as_utc, utcnow

TOKEN_BYTES = 32
TTL = timedelta(days=7)

__all__ = ["TTL", "TOKEN_LENGTH", "create_invite", "find_valid_invite", "invite_context"]


def create_invite(db: Session, tutor_id: str, student_id: str) -> StudentCabinetInvite:
    """Создаёт или перевыпускает приглашение ученика; возвращает строку.

    Повторный вызов при активной ссылке заменяет токен и продлевает срок
    на 7 дней: прежняя ссылка перестаёт работать (D2). `used_at`
    сбрасывается только здесь — погашенное приглашение можно «перевыпустить»
    как повторное, что и есть штатный сброс доступа.
    """
    invite = db.scalars(
        select(StudentCabinetInvite).where(
            StudentCabinetInvite.tutor_id == tutor_id,
            StudentCabinetInvite.student_id == student_id,
        )
    ).first()
    if invite is None:
        invite = StudentCabinetInvite(tutor_id=tutor_id, student_id=student_id)
        db.add(invite)
    invite.token = secrets.token_urlsafe(TOKEN_BYTES)
    invite.expires_at = utcnow() + TTL
    invite.used_at = None
    db.commit()
    return invite


def find_valid_invite(db: Session, token: str) -> StudentCabinetInvite | None:
    """Приглашение по действующему токену; иначе None.

    Действительно: строка существует, не погашена (`used_at` пуст) и срок
    не вышел. Причины недействительности страницы не различают (D9) —
    неизвестный, погашенный и просроченный токен дают одно поведение.
    """
    invite = db.scalars(
        select(StudentCabinetInvite).where(StudentCabinetInvite.token == token)
    ).first()
    if invite is None or invite.used_at is not None:
        return None
    if as_utc(invite.expires_at) <= utcnow():
        return None
    return invite


def invite_context(db: Session, tutor_id: str, student_id: str) -> dict:
    """Данные блока «Личный кабинет» карточки ученика (три состояния).

    Состояния блока: вход не привязан / ссылка активна / вход привязан.
    Вход и активная ссылка не исключают друг друга (вход могли завести
    вручную при живой ссылке) — блок показывает то и другое. Читаются
    только строки приглашений и входа: рендер сетенезависим (D8).
    """
    invite = db.scalars(
        select(StudentCabinetInvite).where(
            StudentCabinetInvite.tutor_id == tutor_id,
            StudentCabinetInvite.student_id == student_id,
        )
    ).first()
    active = (
        invite is not None
        and invite.used_at is None
        and as_utc(invite.expires_at) > utcnow()
    )
    access = get_access(db, student_id)
    return {
        "has_access": access is not None,
        # Идентификаторы привязанного входа: email из приглашения и/или
        # логин из ручной модалки.
        "email": access.email if access else "",
        "login": access.login if access else "",
        "has_invite": active,
        # Токен активной ссылки; построение адреса — в шаблоне блока.
        "token": invite.token if active else "",
    }
