"""Перевод между хранением в UTC и показом времени в зоне педагога.

Единственное место перевода времени в приложении (design D1): ввод формы
трактуется как настенное время в зоне педагога и переводится здесь в UTC;
показ и границы операций считаются в зоне педагога и только результат
переводится в UTC (design D3) — наоборот нельзя: прибавление timedelta к
UTC-значению сдвигало бы дни при переходе на летнее время.

Нормализация чтений — через `as_utc`/`utcnow` из `app/tutor/services/clock.py`:
SQLite теряет tzinfo, поэтому aware-значение существует только в Python и
каждое значение из БД нужно приводить к UTC явно (design D2, Risks).
"""

import os
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.tutor.services.clock import as_utc, utcnow

if TYPE_CHECKING:  # только для аннотации: runtime-зависимости на модуль нет
    from app.tutor.models.tutor import Tutor

# Симлинк системного пояса в дистрибутивах с tzdata; если файла нет или он
# не ведёт в дерево zoneinfo (например, скопирован байт-в-байт), зона
# считается неизвестной и наступает fallback до UTC.
_SYSTEM_ZONE_FILE = Path("/etc/localtime")
_ZONEINFO_MARKER = "/zoneinfo/"


def system_zone_name() -> str | None:
    """IANA-имя системной зоны сервера; определить не удалось — None.

    `datetime.now().astimezone().tzinfo` даёт фиксированное смещение
    (`+04`), а не IANA-имя, поэтому опираемся на источники, где имя есть:
    переменная `TZ` и симлинк `/etc/localtime`.
    """
    raw = os.environ.get("TZ", "").lstrip(":")
    if raw:
        # `TZ` может быть и путём вида /usr/share/zoneinfo/Europe/Berlin.
        return raw.split(_ZONEINFO_MARKER, 1)[1] if _ZONEINFO_MARKER in raw else raw
    try:
        target = os.path.realpath(_SYSTEM_ZONE_FILE)
    except OSError:
        return None
    if _ZONEINFO_MARKER not in target:
        return None
    return target.split(_ZONEINFO_MARKER, 1)[1] or None


def _resolve_zone(name: str | None) -> ZoneInfo:
    """Имя → зона; пустое или неизвестное имя → UTC (последний уровень).

    `ZoneInfoNotFoundError` — не ошибка страницы, а переход к следующему
    уровню fallback (design D2): репетитор со строкой из старого бэкапа
    видит время в UTC, а не 500.
    """
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return UTC


def system_zone() -> ZoneInfo:
    """Системная зона сервера; определить её нельзя — UTC (design D2)."""
    return _resolve_zone(system_zone_name())


def tutor_zone(tutor: "Tutor") -> ZoneInfo:
    """Зона педагога; пустое или неизвестное имя — системная зона сервера."""
    name = getattr(tutor, "timezone", None)
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            pass  # неизвестное имя — не 500, а переход к fallback (design D2)
    return system_zone()


def tutor_zone_name(tutor: "Tutor") -> str:
    """IANA-имя зоны педагога для показа: его карточка либо системная зона.

    Подпись зоны в интерфейсе (бейдж календаря) не должна исчезать при пустом
    поле карточки: показываем системную зону сервера, а определить её не
    удалось — «UTC» (design D2).
    """
    name = getattr(tutor, "timezone", None)
    if name:
        try:
            ZoneInfo(name)
            return name
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            pass
    return system_zone_name() or "UTC"


def to_utc(local_naive: datetime, tutor: "Tutor") -> datetime:
    """Настенное время педагога → aware UTC (design D3/D6).

    Значение трактуется как время в зоне педагога (`replace`, не
    `astimezone`): несуществующие в ночь перевода часов часы `zoneinfo`
    разрешает по `fold=0` без исключения — осознанный компромисс.
    """
    return as_utc(local_naive.replace(tzinfo=tutor_zone(tutor)))


def to_local(value: datetime, tutor: "Tutor") -> datetime:
    """Значение из БД (наивное UTC или aware) → aware в зоне педагога."""
    return as_utc(value).astimezone(tutor_zone(tutor))


def now_utc() -> datetime:
    """Текущий момент в UTC (единый источник «сейчас», design D7)."""
    return utcnow()


def now_local(tutor: "Tutor") -> datetime:
    """Текущий момент в зоне педагога."""
    return now_utc().astimezone(tutor_zone(tutor))


def today_local(tutor: "Tutor") -> date:
    """Текущая календарная дата в зоне педагога."""
    return now_local(tutor).date()


def local_day_bounds(day: date, tutor: "Tutor") -> tuple[datetime, datetime]:
    """Сутки `day` в зоне педагога как интервал aware UTC: [начало, конец).

    Границы считаются как настенное время и переводятся по отдельности
    (design D3): единый сдвиг не учитывает перевод часов.
    """
    return (
        to_utc(datetime.combine(day, time.min), tutor),
        to_utc(datetime.combine(day + timedelta(days=1), time.min), tutor),
    )


def local_week_bounds(monday: date, tutor: "Tutor") -> tuple[datetime, datetime]:
    """Неделя с `monday` (пн–вс включительно) в зоне педагога как aware UTC.

    Конец — это `monday + 7` локально, а не `start + 7 дней`: в неделю с
    переводом часов интервал короче или длиннее ровно на час (design D3).
    """
    return (
        to_utc(datetime.combine(monday, time.min), tutor),
        to_utc(datetime.combine(monday + timedelta(days=7), time.min), tutor),
    )
