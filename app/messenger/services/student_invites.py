"""Приглашение ученика в канал уведомлений: диплинк с одноразовым кодом.

Репетитор в карточке ученика нажимает «Пригласить»: сервис строит диплинк
на его бота (`?start=<код>`) и сохраняет в строке приглашения. Ссылку
отправляют ученику — после «Запуска» бота общая проверка апдейтов
(`binding.confirm_binding`) находит код приглашения и привязывает чат
ученика: напоминания смогут приходить ему лично.

Рендер блока сетенезависим: читаются только строки приглашений; сеть
дёргают `start_invite` и общая проверка привязок.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.messenger.models.student_invite import StudentMessengerInvite
from app.messenger.services.binding import CODE_BYTES, bot_name, ensure_max_marker
from app.messenger.services.errors import BotApiError
from app.messenger.services.messengers import (
    MESSENGER_ICONS,
    MESSENGER_LABELS,
    MESSENGER_LINK_TEMPLATES,
    SUPPORTED,
    token_key,
)
from app.tutor.services.params import get_param


def start_invite(db: Session, tutor_id: str, student_id: str, messenger: str) -> list[str]:
    """Готовит приглашение: одноразовый код и диплинк в строке ученика.

    Повторный вызов до подключения заменяет код и ссылку — старая
    перестаёт работать. Возвращает список ошибок; пустой — ссылка
    готова. Ник бота берётся из сети (getMe / GET /me), поэтому
    неверный токен или недоступная сеть видны сразу.
    """
    if messenger not in SUPPORTED:
        label = MESSENGER_LABELS.get(messenger, messenger)
        return [f"Приглашение в {label} ещё не поддерживается."]
    row = _invite_row(db, tutor_id, student_id, messenger)
    if row.chat_id:
        label = MESSENGER_LABELS[messenger]
        return [f"Ученик уже подключён к {label} — сначала отвяжите канал."]
    token = get_param(db, tutor_id, token_key(messenger))
    if not token:
        label = MESSENGER_LABELS[messenger]
        return [
            f"Сначала создайте бота и вставьте его токен на вкладке "
            f"«Мессенджеры» ({label})."
        ]

    try:
        bot = bot_name(messenger, token)
    except BotApiError as exc:
        return [str(exc)]

    row.invite_code = secrets.token_urlsafe(CODE_BYTES)
    row.invite_link = MESSENGER_LINK_TEMPLATES[messenger].format(
        bot=bot, code=row.invite_code
    )
    if messenger == "max":
        ensure_max_marker(db, tutor_id, token)
    db.commit()
    return []


def unbind_student(db: Session, tutor_id: str, student_id: str, messenger: str) -> None:
    """Удаляет приглашение вместе с привязкой чата и незавершённой ссылкой.

    Токен бота не трогается — он настраивается на вкладке «Мессенджеры».
    """
    row = db.scalar(
        select(StudentMessengerInvite).where(
            StudentMessengerInvite.tutor_id == tutor_id,
            StudentMessengerInvite.student_id == student_id,
            StudentMessengerInvite.messenger == messenger,
        )
    )
    if row is not None:
        db.delete(row)
        db.commit()


def invites_context(db: Session, tutor_id: str, student_id: str) -> dict:
    """Данные блока «Приглашение в мессенджеры»: карточка на каждый
    поддерживаемый мессенджер.

    Рендер сетенезависим: читаются только строки приглашений, сеть дёргают
    `start_invite` и общая проверка привязок по действиям пользователя.
    `errors`/`autocopy` заполняет вьюха после действий; контекст по умолчанию —
    для обычного рендера формы.
    """
    rows = db.scalars(
        select(StudentMessengerInvite).where(
            StudentMessengerInvite.tutor_id == tutor_id,
            StudentMessengerInvite.student_id == student_id,
        )
    ).all()
    by_messenger = {row.messenger: row for row in rows}
    invites = []
    for messenger in SUPPORTED:
        row = by_messenger.get(messenger)
        invites.append({
            "messenger": messenger,
            "label": MESSENGER_LABELS[messenger],
            "icon": MESSENGER_ICONS[messenger],
            # «В процессе» = код сгенерирован, чат ещё не привязан.
            "pending": bool(row and row.invite_code and not row.chat_id),
            "link": (row.invite_link or "") if row else "",
            "bound": bool(row and row.chat_id),
            "chat_label": (row.chat_label or "") if row else "",
        })
    return {"invites": invites, "errors": [], "autocopy": ""}


def _invite_row(
    db: Session, tutor_id: str, student_id: str, messenger: str
) -> StudentMessengerInvite:
    """Строка приглашения пары «ученик — мессенджер»; создаётся лениво."""
    row = db.scalar(
        select(StudentMessengerInvite).where(
            StudentMessengerInvite.student_id == student_id,
            StudentMessengerInvite.messenger == messenger,
        )
    )
    if row is None:
        row = StudentMessengerInvite(
            tutor_id=tutor_id,
            student_id=student_id,
            messenger=messenger,
        )
        db.add(row)
        db.flush()
    return row
