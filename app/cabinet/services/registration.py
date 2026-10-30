"""Регистрация ученика по приглашению: email + пароль → вход в кабинет.

По действующей ссылке ученик задаёт email и пароль. Входа ещё нет —
создаётся строка `StudentAccess`; вход уже есть (заведён вручную) —
обновляются `email` и пароль, карточка та же (D3): «повторное приглашение»
— штатный сброс доступа. Погашение токена и запись входа — одна
транзакция: ссылка не может остаться действующей при несохранившемся входе.

Логин при создании входа по приглашению остаётся равен email: колонка
`login` NOT NULL, а паттерн ручной модалки на этот путь не
распространяется. Идентификация при входе не ломается — адрес не
зависит от содержимого колонок: идентификатор с `@` ищется по `email`,
без `@` — по `login`.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cabinet.models.invite import StudentCabinetInvite
from app.student.models.student_access import MIN_PASSWORD_LENGTH, StudentAccess
from app.tutor.services.password_hasher import PasswordHasher
from app.tutor.services.clock import utcnow

# Проверка формата: что-то@что-то.что. Полноценной проверки доставляемости
# нет и не нужно — email здесь идентификатор входа, а не адрес рассылки.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

ERROR_EMAIL_FORMAT = "Укажите корректный email."
ERROR_EMAIL_TAKEN = "Этот email уже используется."
ERROR_PASSWORD_SHORT = f"Пароль — минимум {MIN_PASSWORD_LENGTH} символов."
# Ссылка перестала действовать между показом формы и отправкой: её открыли
# из двух вкладок, погасили перевыпуском или удалили. Валидность приглашения
# перечитывается в транзакции регистрации (см. `register_by_invite`).
ERROR_LINK_INVALID = "Ссылка недействительна."


def email_taken(db: Session, email: str, *, exclude_student_id: str = "") -> bool:
    """Email уже привязан к другому входу (по образцу `login_taken`).

    UNIQUE-индекс остаётся страховкой от гонки двух одновременных
    регистраций с одним email.
    """
    stmt = select(StudentAccess).where(StudentAccess.email == email.strip())
    if exclude_student_id:
        stmt = stmt.where(StudentAccess.student_id != exclude_student_id)
    return db.scalars(stmt.limit(1)).first() is not None


def register_by_invite(
    db: Session,
    invite: StudentCabinetInvite,
    email: str,
    password: str,
) -> list[str]:
    """Привязывает вход к карточке ученика по действующему приглашению.

    Возвращает список ошибок; пустой — вход записан, токен погашен,
    транзакция закоммичена. Ошибка валидации — ничего не меняется.

    Приглашение перечитывается по токену в своей транзакции: переданный
    объект мог прийти из другой сессии (отсоединённым), а публичный
    эндпоинт обязан отвергнуть гонку двух одновременных регистраций по
    одной ссылке — погашенный токен не пройдёт вторично.
    """
    email_value = email.strip()
    errors: list[str] = []
    if not EMAIL_PATTERN.match(email_value):
        errors.append(ERROR_EMAIL_FORMAT)
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(ERROR_PASSWORD_SHORT)
    if errors:
        return errors

    invite = db.scalars(
        select(StudentCabinetInvite).where(StudentCabinetInvite.token == invite.token)
    ).first()
    if invite is None or invite.used_at is not None:
        return [ERROR_LINK_INVALID]

    existing = db.scalars(
        select(StudentAccess).where(
            StudentAccess.student_id == invite.student_id
        )
    ).first()
    if existing is not None:
        if email_taken(db, email_value, exclude_student_id=existing.student_id):
            return [ERROR_EMAIL_TAKEN]
        existing.email = email_value
        existing.password_hash = PasswordHasher().hash(password)
    else:
        if email_taken(db, email_value):
            return [ERROR_EMAIL_TAKEN]
        db.add(
            StudentAccess(
                student_id=invite.student_id,
                login=email_value,
                email=email_value,
                password_hash=PasswordHasher().hash(password),
            )
        )

    invite.used_at = utcnow()
    db.commit()
    return []
