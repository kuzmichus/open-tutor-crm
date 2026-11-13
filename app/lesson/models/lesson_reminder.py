"""Модель «Отправленное напоминание о начале урока».

Одна строка на пару «урок + интервал + получатель»: она и есть маркер
«напоминание уже отправлено». Отдельная таблица, а не параметр
репетитора в `tutor_params`: напоминаний много, они привязаны к уроку и
умирают вместе с ним каскадом, а маркер в KV-таблице пришлось бы
составлять из строки ключа и чистить вручную.

Уникальное ограничение — второй рубеж идемпотентности: минутные прогоны
cron могут наложиться, и INSERT дубля не пройдёт даже если проверка
«уже отправлено» в сервисе разминулась с параллельным прогоном.
`recipient_id` — id репетитора (`audience='tutor'`) или ученика
(`audience='student'`): отдельная колонка вместо nullable-ссылки, потому
что SQLite не сравнивает NULL в UNIQUE и дубли прошли бы.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.constraints import sql_int_in, sql_string_in
from app.database import Base
from app.tutor.models.tutor_settings import REMINDER_OFFSETS

# Кому уходит напоминание: репетитору или ученику.
REMINDER_AUDIENCES = ("tutor", "student")


class LessonReminder(Base):
    """Факт отправки напоминания: урок, интервал, получатель и время.

    `offset_min` — интервал из настроек репетитора (15 / 60 / 1440 минут),
    а не фактический остаток времени. Поэтому текст догоняющего сообщения
    не меняется, даже если тик cron был пропущен.
    """

    __tablename__ = "lesson_reminders"
    __table_args__ = (
        UniqueConstraint(
            "lesson_id",
            "offset_min",
            "audience",
            "recipient_id",
            name="uq_lesson_reminders_target",
        ),
        CheckConstraint(
            sql_int_in("offset_min", REMINDER_OFFSETS),
            name="ck_lesson_reminders_offset",
        ),
        CheckConstraint(
            sql_string_in("audience", REMINDER_AUDIENCES),
            name="ck_lesson_reminders_audience",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Удаление урока уносит его напоминания: история отдельного урока
    # никому не нужна, а строки без урока были бы мусором.
    lesson_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("lessons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    offset_min: Mapped[int] = mapped_column(Integer, nullable=False)
    audience: Mapped[str] = mapped_column(String(8), nullable=False)
    # FK нет: получатель полиморфен (репетитор или ученик). Целостность
    # держит каскад урока — без урока маркер не нужен в любом случае.
    recipient_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<LessonReminder lesson_id={self.lesson_id!r} "
            f"offset_min={self.offset_min} audience={self.audience!r}>"
        )