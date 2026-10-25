"""Вход ученика: валидация, генерация пароля, сохранение.

Сервис не знает про FastAPI: на вход — `Session` и очищенные значения,
на выход — данные или список ошибок (как `student_form`). Хеширование —
общий `PasswordHasher` репетитора: в проекте одна хеш-схема, и будущий
кабинет ученика сможет переиспользовать и её, и правила сложности.

Логин уникален глобально (модель `StudentAccess`): проверка делается
`SELECT`-ом, чтобы репетитор получил внятное сообщение в форме, а
UNIQUE-индекс остаётся страховкой от гонки двух одновременных сохранений.
"""

import re
import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.student.models.student_access import (
    MIN_LOGIN_LENGTH,
    MIN_PASSWORD_LENGTH,
    StudentAccess,
)
from app.tutor.services.password_hasher import PasswordHasher

# Логин кабинета: латиница, цифры и подчёркивание (по референсу модалки).
LOGIN_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")

# Алфавит генератора пароля: без похожих символов (0/O/o, 1/l/I), чтобы
# пароль можно было надиктовать по телефону без «ноль как буква О».
_PASSWORD_ALPHABET = (
    string.ascii_letters.replace("o", "")
    .replace("O", "")
    .replace("l", "")
    .replace("I", "")
    + string.digits.replace("0", "").replace("1", "")
)

# Ошибки формы (по одной на поле либо общая — паттерн `student_form`).
ERROR_LOGIN_FORMAT = (
    "Логин — только латиница, цифры и «_», минимум 3 символа."
)
ERROR_LOGIN_TAKEN = "Такой логин уже занят."
ERROR_PASSWORD_SHORT = f"Пароль — минимум {MIN_PASSWORD_LENGTH} символов."


def validate_login(login: str) -> list[str]:
    """Ошибки логина; пустой список — значение корректно."""
    value = login.strip()
    if (
        len(value) < MIN_LOGIN_LENGTH
        or not LOGIN_PATTERN.match(value)
    ):
        return [ERROR_LOGIN_FORMAT]
    return []


def validate_password(password: str) -> list[str]:
    """Ошибки пароля; пустой список — значение корректно."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return [ERROR_PASSWORD_SHORT]
    return []


def generate_password(length: int = 12) -> str:
    """Случайный пароль из безопасного алфавита (кнопка «Сгенерировать»)."""
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def get_access(db: Session, student_id: str) -> StudentAccess | None:
    """Вход ученика; входа ещё нет — `None`."""
    return db.scalars(
        select(StudentAccess).where(StudentAccess.student_id == student_id)
    ).first()


def login_taken(db: Session, login: str, *, exclude_student_id: str = "") -> bool:
    """Логин уже занят кем-то, кроме указанного ученика (смена пароля)."""
    stmt = select(StudentAccess).where(StudentAccess.login == login.strip())
    if exclude_student_id:
        stmt = stmt.where(StudentAccess.student_id != exclude_student_id)
    return db.scalars(stmt.limit(1)).first() is not None


def save_access(
    db: Session,
    student_id: str,
    login: str,
    password: str,
) -> list[str]:
    """Создаёт или обновляет вход ученика; без коммита (путь вызова — вьюха).

    Пустой пароль при существующем входе означает «оставить старый»:
    смена пароля — осознанное действие, а каждое открытие модалки не
    должно требовать придумать новый. Возвращает список ошибок; ошибки —
    форма не сохраняется.
    """
    errors = validate_login(login)
    login_value = login.strip()
    existing = get_access(db, student_id)

    # Пустой пароль при существующем входе = «оставить старый»; при создании
    # пустой пароль — ошибка (короче минимума).
    if existing is not None and not password:
        password_errors: list[str] = []
    else:
        password_errors = validate_password(password)
    errors += password_errors

    if not errors and login_taken(
        db, login_value, exclude_student_id=student_id
    ):
        errors.append(ERROR_LOGIN_TAKEN)
    if errors:
        return errors

    if existing is None:
        db.add(
            StudentAccess(
                student_id=student_id,
                login=login_value,
                password_hash=PasswordHasher().hash(password),
            )
        )
    else:
        existing.login = login_value
        if password:
            existing.password_hash = PasswordHasher().hash(password)
    return []
