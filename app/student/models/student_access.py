"""Модель «Вход ученика» (логин/пароль личного кабинета).

У входа две равноправные идентичности (D1 change'а student-cabinet-access):
`login` — из ручной модалки «Доступ ученика», `email` — из регистрации по
приглашению; пароль один на строку. Форма входа кабинета принимает
«идентификатор»: содержит `@` — поиск по `email`, иначе по `login` —
пространства имён не пересекаются, потому что логин по паттерну модалки
не может содержать `@`. Обе колонки уникальны по всей базе: кабинет
входит по паре «идентификатор + пароль» без указания репетитора, поэтому
`petya` и `petya@…` у двух репетиторов сделали бы вход неоднозначным.

Пароль открытым текстом не хранится никогда: показать его второй раз
невозможно в принципе, что совпадает с правилом «данные показываются
один раз». Хеш — PBKDF2, общий `PasswordHasher` репетитора: второй
хеш-схемы в проекте не нужно.

Закрытые списки значений здесь не нужны: ограничение логина —
`LOGIN_PATTERN` в `app/student/services/credentials.py`, а в БД его
держит CHECK по длине (формат регэкспом в SQL не проверяют — заглавные/
строчные уже покрыты индексом уникальности).
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Минимальная длина логина и пароля: источник истины для CHECK-ограничения
# БД и для валидации формы (credentials.validate_login/validate_password).
MIN_LOGIN_LENGTH = 3
MIN_PASSWORD_LENGTH = 8


class StudentAccess(Base):
    """Вход ученика в личный кабинет: логин и хеш пароля.

    `student_id` уникален: у ученика ровно один вход, повторное сохранение
    меняет пароль, а не создаёт второй. Удаление ученика каскадом уносит
    вход — осиротевший логин без владельца был бы дырой в уникальности.
    """

    __tablename__ = "student_access"
    __table_args__ = (
        CheckConstraint(
            f"length(login) >= {MIN_LOGIN_LENGTH}",
            name="ck_student_access_login_length",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Ровно один вход на ученика (ux_student_access_student).
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # Уникален глобально: будущий кабинет входит без указания репетитора.
    login: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # Вторая идентичность входа (D1): задаётся при регистрации по
    # приглашению. Nullable — вход может существовать только с логином
    # (ручная модалка); уникальность — уникальным индексом, как у
    # `students.email`: SQLite не умеет добавлять CONSTRAINT к живой
    # таблице, а индекс создаётся и удаляется штатно.
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, unique=True
    )
    # Формат `pbkdf2_sha256$итерации$соль$хеш` (PasswordHasher).
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<StudentAccess id={self.id} login={self.login!r}>"
