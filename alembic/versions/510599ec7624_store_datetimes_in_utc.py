"""store datetimes in UTC: сдвиг lessons.starts_at и homework.due_at

Существующие значения `starts_at`/`due_at` хранятся как настенное время
сервера (`datetime-local` из формы кладётся в БД как есть). Миграция
трактует каждое значение как настенное время в зоне-источнике, переводит
в UTC и заполняет `tutors.timezone` этой же зоной — после неё отображение
не меняется ни на минуту (design D8).

Зона-источник берётся из `MIGRATION_SOURCE_TZ`, иначе — системная зона
сервера; имя печатается в лог, иначе результат сдвига невоспроизводим.
Логика зоны намеренно не импортирует приложение: миграция обязана
оставаться самодостаточной, пока живёт в архиве ревизий.

Revision ID: 510599ec7624
Revises: e8ae8f952073
Create Date: 2026-10-22 10:00:00.000000

"""
import os
from datetime import UTC
from typing import Sequence, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '510599ec7624'
down_revision: Union[str, Sequence[str], None] = 'e8ae8f952073'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Моменты времени: (таблица, колонка). Календарные даты (unavailability,
# until_date, joined) — нет: у них нет смещения, их сдвигать нельзя.
_SHIFTED_COLUMNS = (("lessons", "starts_at"), ("homework", "due_at"))

_ZONEINFO_MARKER = "/zoneinfo/"


def _system_zone_name() -> str:
    """IANA-имя системного пояса сервера; определить не удалось — 'UTC'."""
    raw = os.environ.get("TZ", "").lstrip(":")
    if raw:
        return raw.split(_ZONEINFO_MARKER, 1)[1] if _ZONEINFO_MARKER in raw else raw
    try:
        target = os.path.realpath("/etc/localtime")
    except OSError:
        return "UTC"
    if _ZONEINFO_MARKER not in target:
        return "UTC"
    return target.split(_ZONEINFO_MARKER, 1)[1] or "UTC"


def _source_zone() -> ZoneInfo:
    """Зона-источник сдвига: MIGRATION_SOURCE_TZ, иначе системная, иначе UTC.

    Имя печатается в лог: без него сдвиг невоспроизводим и непроверяем
    (design D8). Неизвестное имя не роняет миграцию — наступает UTC.
    """
    name = os.environ.get("MIGRATION_SOURCE_TZ", "").lstrip(":") or _system_zone_name()
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        zone = ZoneInfo("UTC")
    # print, а не logging: виден в обычном выводе `alembic upgrade head`
    # без настройки логгеров.
    print(f"[store-datetimes-in-utc] зона-источник сдвига: {zone.key}")
    return zone


def _shift(bind, zone: ZoneInfo, *, to_utc: bool) -> None:
    """Построчный перевод колонок между настенном временем зоны и UTC.

    Перевод по каждой строке, а не единым смещением: строки из разных
    сезонов могут попадать по разные стороны перехода на летнее время
    (design D8, п. 2). `to_utc=False` — обратный перевод для downgrade.
    """
    metadata = sa.MetaData()
    for table_name, column_name in _SHIFTED_COLUMNS:
        table = sa.Table(
            table_name,
            metadata,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(column_name, sa.DateTime(timezone=True)),
            autoload_with=bind,
        )
        column = table.c[column_name]
        rows = bind.execute(
            sa.select(table.c.id, column).where(column.is_not(None))
        ).fetchall()
        for row_id, value in rows:
            if to_utc:
                # Наивное значение из SQLite — настенное время зоны-источника.
                converted = value.replace(tzinfo=zone).astimezone(UTC)
            else:
                # Обратно: UTC-момент → настенное время зоны-источника.
                utc_value = value if value.tzinfo else value.replace(tzinfo=UTC)
                converted = utc_value.astimezone(zone).replace(tzinfo=None)
            bind.execute(
                sa.update(table)
                .where(table.c.id == row_id)
                .values({column_name: converted})
            )


def upgrade() -> None:
    """Сдвиг данных в UTC и заполнение часов пояса репетиторов."""
    bind = op.get_bind()
    zone = _source_zone()
    _shift(bind, zone, to_utc=True)
    bind.execute(
        sa.text("UPDATE tutors SET timezone = :timezone"),
        {"timezone": zone.key},
    )


def downgrade() -> None:
    """Обратный перевод в настенное время зоны-источника и сброс зоны."""
    bind = op.get_bind()
    zone = _source_zone()
    _shift(bind, zone, to_utc=False)
    bind.execute(sa.text("UPDATE tutors SET timezone = NULL"))
