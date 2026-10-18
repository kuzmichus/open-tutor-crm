"""Список часовых зон для поля «Часовой пояс».

Источник — IANA TZDB из стандартной библиотеки (`zoneinfo`): то же дерево
часовых зон, что в системе. Никакого хардкода сотен строк и внешних
зависимостей — новый релиз tzdata подхватывается вместе с Python.

Подпись зоны — смещение от UTC (`UTC+03:00`): без него имя `Europe/Berlin`
мало что говорит пользователю, а рядом с `Europe/Moscow` сразу видно разницу.
"""

from datetime import datetime
from functools import lru_cache
from json import dumps
from zoneinfo import ZoneInfo, available_timezones

# `localtime` — системный псевдоним локального пояса, а не часовой пояс:
# в списке он только путает.
_NOT_A_TIMEZONE = {"localtime"}


def _offset_minutes(name: str) -> int:
    """Текущее смещение пояса от UTC в минутах (с учётом летнего времени)."""
    offset = datetime.now(ZoneInfo(name)).utcoffset()
    return 0 if offset is None else int(offset.total_seconds()) // 60


def _utc_label(minutes: int) -> str:
    """Подпись смещения вида `UTC+03:00` / `UTC-05:30`."""
    sign = "+" if minutes >= 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours:02d}:{rest:02d}"


@lru_cache(maxsize=1)
def timezone_options() -> tuple[tuple[str, str], ...]:
    """Пары (IANA-имя, подпись смещения) для селекта с поиском.

    Смещение текущее — на момент первого вызова (кэш живёт до перезапуска
    процесса): зоны с переходом на летнее время показываются со сдвигом
    на сегодня.

    Сортировка — по смещению, затем по имени: рядом оказываются зоны с
    одинаковым временем, а не случайный порядок каталога.
    """
    rows = [
        (_offset_minutes(name), name)
        for name in available_timezones()
        if name not in _NOT_A_TIMEZONE
    ]
    rows.sort()
    return tuple((name, _utc_label(minutes)) for minutes, name in rows)


@lru_cache(maxsize=1)
def timezone_options_json() -> str:
    """JSON-массив `[{value, label}, ...]` для клиентского селекта.

    Кавычки экранирует сам шаблон (автоэкранирование Jinja в атрибуте),
    здесь нужен только валидный JSON; не-ASCII в нём не бывает.
    """
    return dumps(
        [{"value": name, "label": label} for name, label in timezone_options()],
        ensure_ascii=False,
        separators=(",", ":"),  # компактнее: список уезжает в атрибут формы
    )
