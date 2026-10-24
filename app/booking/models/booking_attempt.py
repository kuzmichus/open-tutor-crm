"""Модель «Счётчик попыток записи» (design.md D12).

Публичная форма записи — единственный неаутентифицированный маршрут,
создающий строки. Полноценного rate limiting в проекте нет, а тянуть
Redis ради счётчика неоправданно: таблица в той же SQLite закрывает
сценарий «одна ссылка в чате и сотня заявок».

Ключ — `sha256(slot_id + грубый отпечаток клиента)`: лимит считается на
конкретное окно, поэтому перебор разных окон одним клиентом не блокирует
обычную запись. Строки старше суток удаляются при каждом обращении —
отдельного планировщика нет.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Окно подсчёта и лимит заявок в нём (design.md D12).
BOOKING_ATTEMPT_WINDOW_MIN = 10
BOOKING_ATTEMPT_LIMIT = 5
# Срок хранения счётчиков: старше суток строки не нужны ни одной проверке.
BOOKING_ATTEMPT_RETENTION_HOURS = 24


class BookingAttempt(Base):
    """Счётчик заявок по ключу «окно + отпечаток клиента» за окно времени.

    `UNIQUE(key, window_start)` не даёт двум параллельным запросам завести
    две строки на одно окно: второй падает на ограничении и обрабатывается
    тем же путём, что и обычное инкрементирование.
    """

    __tablename__ = "booking_attempts"
    __table_args__ = (
        UniqueConstraint("key", "window_start", name="uq_booking_attempts_key"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # sha256 в hex — 64 символа; сам slot_id и адрес клиента не хранятся.
    key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<BookingAttempt key={self.key[:8]}… "
            f"window_start={self.window_start!r} count={self.count}>"
        )
