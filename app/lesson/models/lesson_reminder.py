"""Модель «Доставка напоминания о начале урока в канал получателя».

Одна строка на пару «урок + интервал + получатель + канал»: она же
маркер «напоминание уже доставлено в этот канал». Отдельная таблица, а не
параметр репетитора в `tutor_params`: напоминаний много, они привязаны к
уроку и умирают вместе с ним каскадом, а маркер в KV-таблице пришлось бы
составлять из строки ключа и чистить вручную.

Строка живёт в двух состояниях:

- `claimed_at` заполнен, `delivered_at` пуст — доставка захвачена
  прогоном cron. Захват коммитится **до** обращения к мессенджеру, поэтому
  второй (наложившийся) прогон видит строку и не отправляет дубль; если
  прогон упал, захват истекает через `REMINDER_CLAIM_LEASE` и доставка
  повторяется — это и есть политика восстановления;
- `delivered_at` заполнен — сообщение доставлено, повторов нет.

Уникальное ограничение по каналу — второй рубеж идемпотентности:
параллельные прогоны не могут вставить два захвата на один канал, даже
если проверка «уже отправлено» разминулась. `recipient_id` — id
репетитора (`audience='tutor'`) или ученика (`audience='student'`):
отдельная колонка вместо nullable-ссылки, потому что SQLite не сравнивает
NULL в UNIQUE и дубли прошли бы.

Доставка фиксируется по каналу, а не по получателю целиком: при сбое
одного мессенджера второй получает сообщение сразу, а сбойный
повторяется следующим прогоном, не дублируя уже доставленное.
"""

from datetime import UTC, datetime, timedelta
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
from app.messenger.services.messengers import MESSENGERS
from app.tutor.models.tutor_settings import REMINDER_OFFSETS

# Кому уходит напоминание: репетитору или ученику.
REMINDER_AUDIENCES = ("tutor", "student")

# Сколько живёт захват доставки без подтверждения. Меньше интервала между
# прогонами смысла нет (повторяли бы каждую минуту и долбили лежащий API),
# больше — рискуем не успеть повторить до начала урока. Пять минут дают
# несколько попыток даже для пятнадцатиминутного напоминания.
REMINDER_CLAIM_LEASE = timedelta(minutes=5)


class LessonReminder(Base):
    """Доставка напоминания в канал: урок, интервал, получатель, канал.

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
            "channel",
            name="uq_lesson_reminders_channel",
        ),
        CheckConstraint(
            sql_int_in("offset_min", REMINDER_OFFSETS),
            name="ck_lesson_reminders_offset",
        ),
        CheckConstraint(
            sql_string_in("audience", REMINDER_AUDIENCES),
            name="ck_lesson_reminders_audience",
        ),
        CheckConstraint(
            sql_string_in("channel", MESSENGERS),
            name="ck_lesson_reminders_channel",
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
    # Мессенджер доставки. Строка создаётся захватом, поэтому NOT NULL:
    # «напоминание получателю вообще» без канала не существует.
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    # NULL — ещё не доставлено: захват в работе или попытка не удалась.
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<LessonReminder lesson_id={self.lesson_id!r} "
            f"offset_min={self.offset_min} audience={self.audience!r} "
            f"channel={self.channel!r} delivered={self.delivered_at is not None}>"
        )
