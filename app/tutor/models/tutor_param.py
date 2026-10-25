"""Модель «Параметр репетитора»: общее KV-хранилище настроек."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TutorParam(Base):
    """Произвольный параметр репетитора — одна строка на пару (репетитор, ключ).

    В отличие от широкой `tutor_settings` (колонки с дефолтами и CHECK),
    здесь живут необязательные параметры без фиксированного набора:
    токены мессенджеров (`telegram_token`, …) и будущие настройки. Новый
    параметр — новая строка, миграция на каждый ключ не нужна.

    Составной PK делает upsert естественным: второй INSERT с тем же
    (tutor_id, key) невозможен, запись идёт через сервис
    `app.tutor.services.params`.
    """

    __tablename__ = "tutor_params"

    tutor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tutors.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # Ключ — короткое имя параметра («telegram_token»). Открытый список:
    # набор ключей задаётся сервисами, а не БД, поэтому CHECK не ставится.
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    # Text, а не String: значение может быть длиннее токена (ссылка,
    # JSON-фрагмент) — ограничивать длину заранее нечем.
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<TutorParam tutor_id={self.tutor_id!r} key={self.key!r}>"
