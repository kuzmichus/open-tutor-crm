"""Приглашение контакта в кабинет родителя: одноразовая ссылка `/parent/invite/<token>`.

Копия сервиса приглашения ученика с заменой ученик → контакт (design D2):
одна строка на контакт, «Создать приглашение» при активной ссылке обновляет
`token` и `expires_at` — прежняя гасится сама. Рендер состояния
сетенезависим: читаются только строки БД, сеть не дёргается.
"""

import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.models.contact_access import ContactAccess
from app.cabinet.models.contact_invite import TOKEN_LENGTH, ContactCabinetInvite
from app.tutor.services.clock import as_utc, utcnow

TOKEN_BYTES = 32
TTL = timedelta(days=7)

__all__ = ["TTL", "TOKEN_LENGTH", "badge_contexts", "create_invite", "find_valid_invite"]


def _is_active(invite: ContactCabinetInvite | None) -> bool:
    """Ссылка жива: строка есть, не погашена и срок не вышел."""
    return (
        invite is not None
        and invite.used_at is None
        and as_utc(invite.expires_at) > utcnow()
    )


def create_invite(db: Session, tutor_id: str, contact_id: str) -> ContactCabinetInvite:
    """Создаёт или перевыпускает приглашение контакта; возвращает строку.

    Повторный вызов при активной ссылке заменяет токен и продлевает срок
    на 7 дней: прежняя ссылка перестаёт работать (D2). `used_at`
    сбрасывается только здесь — погашенное приглашение можно «перевыпустить»
    как повторное, что и есть штатный сброс доступа.
    """
    invite = db.scalars(
        select(ContactCabinetInvite).where(
            ContactCabinetInvite.tutor_id == tutor_id,
            ContactCabinetInvite.contact_id == contact_id,
        )
    ).first()
    if invite is None:
        invite = ContactCabinetInvite(tutor_id=tutor_id, contact_id=contact_id)
        db.add(invite)
    invite.token = secrets.token_urlsafe(TOKEN_BYTES)
    invite.expires_at = utcnow() + TTL
    invite.used_at = None
    db.commit()
    return invite


def find_valid_invite(db: Session, token: str) -> ContactCabinetInvite | None:
    """Приглашение по действующему токену; иначе None.

    Действительно: строка существует, не погашена (`used_at` пуст) и срок
    не вышел. Причины недействительности страницы не различают —
    неизвестный, погашенный и просроченный токен дают одно поведение.
    """
    invite = db.scalars(
        select(ContactCabinetInvite).where(ContactCabinetInvite.token == token)
    ).first()
    return invite if _is_active(invite) else None


def badge_contexts(db: Session, tutor_id: str, contact_ids: list[str]) -> dict[str, dict]:
    """Состояние бейджа «Личный кабинет» для списка контактов.

    Возвращает словарь `contact_id → {has_access, email, has_invite, token}`.
    Два SELECT на весь список (приглашения и входы контактов репетитора,
    отфильтрованные по `contact_id`), без N+1 на строку — бейджи
    рендерятся в форме ученика пачкой (D3). Состояния не исключают друг
    друга: у контакта может быть и вход, и активная ссылка (её держат
    про запас или для сброса пароля).

    Контакты без строк в словаре отсутствуют — вызывающий строит состояние
    «нет входа» по умолчанию.
    """
    if not contact_ids:
        return {}

    invites = db.scalars(
        select(ContactCabinetInvite).where(
            ContactCabinetInvite.tutor_id == tutor_id,
            ContactCabinetInvite.contact_id.in_(contact_ids),
        )
    ).all()
    accesses = db.scalars(
        select(ContactAccess).where(ContactAccess.contact_id.in_(contact_ids))
    ).all()

    contexts: dict[str, dict] = {
        contact_id: {"has_access": False, "email": "", "has_invite": False, "token": ""}
        for contact_id in contact_ids
    }
    for access in accesses:
        contexts[access.contact_id]["has_access"] = True
        contexts[access.contact_id]["email"] = access.email
    for invite in invites:
        if _is_active(invite):
            contexts[invite.contact_id]["has_invite"] = True
            contexts[invite.contact_id]["token"] = invite.token
    return contexts
