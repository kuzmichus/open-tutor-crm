"""Модель «Снимок прогноза» (вкладка «Прогноз на месяц»).

Кнопка «Зафиксировать прогноз» сохраняет текущий диапазон выручки на
месяц: позже, когда часть месяца станет фактом, карточка «Прогноз vs
факт» сравнит зафиксированные числа с реальными списаниями. Без снимка
сравнивать не с чем — прогноз пересчитывается на каждый запрос и всегда
говорил бы «факт в норме».

Один снимок на пару «репетитор + месяц» (`uq_forecast_snapshots_period`):
повторная фиксация того же месяца не плодит строки, а заменяет снимок —
карточка всегда показывает последний прогноз.

Диапазон хранится двумя целыми (нижняя/верхняя граница), а не строкой:
прогноз — числа, и сравнение факта с границами идёт в сервисе, а не
разбором форматированной строки.
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

from app.database import Base

# Границы номера месяца — один источник истины для CHECK-ограничения.
MIN_MONTH = 1
MAX_MONTH = 12


class ForecastSnapshot(Base):
    """Зафиксированный вручную прогноз выручки на календарный месяц."""

    __tablename__ = "forecast_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tutor_id", "year", "month", name="uq_forecast_snapshots_period"
        ),
        CheckConstraint(
            f"month BETWEEN {MIN_MONTH} AND {MAX_MONTH}",
            name="ck_forecast_snapshots_month",
        ),
        CheckConstraint("revenue_low <= revenue_high", name="ck_forecast_snapshots_range"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    # Владелец снимка; удаление репетитора каскадом уносит его снимки.
    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Календарный месяц снимка в зоне педагога (месяц — пара год/номер).
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    # Диапазон ожидаемой выручки за месяц, рубли.
    revenue_low: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_high: Mapped[int] = mapped_column(Integer, nullable=False)
    # Момент фиксации: подпись «Снимок от 26.10, 02:04» и признак «ручной».
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ForecastSnapshot id={self.id} tutor_id={self.tutor_id!r} "
            f"{self.year}-{self.month:02d} "
            f"low={self.revenue_low} high={self.revenue_high}>"
        )
