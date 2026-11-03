"""Цвет события Google из цвета цели урока: чистые функции без БД и HTTP.

Задача — чтобы расписание в телефоне читалось так же, как календарь CRM:
ученик и группа имеют свой цвет (`students.color`/`groups.color`), и
событие занятия красится в ближайший к нему цвет Google.

Палитры не совпадают: у CRM 16 оттенков, у Google Calendar API 11
`colorId` событий (`colors.event`). Поэтому точное совпадение hex ищется
по таблице, а всё остальное сводится к ближайшему цвету Google по
расстоянию в CIELAB — перцептивном пространстве, где «на глаз» разница
ближе к евклидовой метрике, чем в RGB.

Почему не режим CRM «по статусу» (`?color=status`): режим живёт в
localStorage браузера, сервер о нём не знает, а статус меняется без
правки события. В Google уходит стабильный цвет цели — режим по умолчанию.
"""

from app.common.colors import DEFAULT_TARGET_COLOR

# Палитра событий Google Calendar API v3 (`colors.event`), 11 цветов.
# Значения — из документации API; собраны в одном месте, чтобы смена
# палитры Google была правкой в одну строку.
GOOGLE_EVENT_COLORS: dict[str, str] = {
    "1": "#a4bdfc",   # Lavender
    "2": "#7ae7bf",   # Sage
    "3": "#dbadff",   # Grape
    "4": "#ff887c",   # Flamingo
    "5": "#fbd75b",   # Banana
    "6": "#ffb878",   # Tangerine
    "7": "#46d6db",   # Peacock
    "8": "#e1e1e1",   # Graphite
    "9": "#5484ed",   # Blueberry
    "10": "#51b749",  # Basil
    "11": "#dc2127",  # Tomato
}

# Цвет Google по умолчанию: ближайший к `DEFAULT_TARGET_COLOR` CRM.
DEFAULT_COLOR_ID = "9"

# Соответствие 16 цветов палитры CRM и цвета по умолчанию цветам Google:
# hex → colorId. Таблица закрепляет «человеческий» выбор там, где
# расстояние в CIELAB даёт спорный результат (например, #8c3cdd ближе к
# Blueberry, но по смыслу это Grape), и делает поведение предсказуемым.
PALETTE_COLOR_IDS: dict[str, str] = {
    "#dd3c3c": "11",  # Tomato
    "#dd783c": "6",   # Tangerine
    "#ddb43c": "5",   # Banana
    "#c8dd3c": "5",   # Banana
    "#8cdd3c": "2",   # Sage
    "#50dd3c": "10",  # Basil
    "#3cdd64": "10",  # Basil
    "#3cdda0": "2",   # Sage
    "#3cdddd": "7",   # Peacock
    "#3ca0dd": "1",   # Lavender
    "#3c64dd": "9",   # Blueberry
    "#503cdd": "9",   # Blueberry
    "#8c3cdd": "3",   # Grape
    "#c83cdd": "3",   # Grape
    "#dd3cb4": "3",   # Grape
    "#dd3c78": "4",   # Flamingo
    DEFAULT_TARGET_COLOR: "9",  # Blueberry
}

# Порядок цветов Google для детерминированного выбора при равном
# расстоянии: перебор идёт по возрастанию colorId.
_COLOR_IDS = tuple(GOOGLE_EVENT_COLORS)

def color_id(color: str | None) -> str:
    """`colorId` события Google для цвета цели урока.

    Пустое или некорректное значение (у старых записей `color` = NULL)
    даёт цвет по умолчанию CRM, а не ошибку: событие всё равно должно
    создаться. Результат — всегда строка из набора «1»–«11», как ждёт API.
    """
    normalized = _normalize(color)
    if normalized is None:
        return DEFAULT_COLOR_ID
    exact = PALETTE_COLOR_IDS.get(normalized)
    if exact is not None:
        return exact
    return _nearest(normalized)

def _normalize(color: str | None) -> str | None:
    """hex в нижний регистр с `#`; `None`, если значение не похоже на hex.

    Пробелы по краям срезаются: цвет мог прийти из формы или старой
    записи с лишним пробелом.
    """
    if not isinstance(color, str):
        return None
    value = color.strip().lower()
    if not value.startswith("#"):
        value = f"#{value}"
    if len(value) != 7:
        return None
    try:
        int(value[1:], 16)
    except ValueError:
        return None
    return value

def _nearest(color: str) -> str:
    """Ближайший цвет Google по расстоянию в CIELAB."""
    target = _lab(color)
    return min(
        _COLOR_IDS,
        key=lambda cid: _distance(target, _lab(GOOGLE_EVENT_COLORS[cid])),
    )

def _distance(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> float:
    """Квадрат евклидова расстояния в CIELAB: корень не нужен для минимума."""
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))

def _lab(color: str) -> tuple[float, float, float]:
    """sRGB hex → CIELAB (D65): перевод через линейный RGB и XYZ."""
    red, green, blue = (_linear(color[index:index + 2]) for index in (1, 3, 5))
    x = red * 0.4124564 + green * 0.3575761 + blue * 0.1804375
    y = red * 0.2126729 + green * 0.7151522 + blue * 0.0721750
    z = red * 0.0193339 + green * 0.1191920 + blue * 0.9503041
    fx, fy, fz = (
        _f(value / white)
        for value, white in ((x, 0.95047), (y, 1.0), (z, 1.08883))
    )
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))

def _linear(channel: str) -> float:
    """Канал 0–255 → линейная яркость по sRGB (гамма 2.4)."""
    value = int(channel, 16) / 255
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4

def _f(value: float) -> float:
    """Компрессия XYZ для CIELAB (порог 6/29)."""
    if value > (6 / 29) ** 3:
        return value ** (1 / 3)
    return value / (3 * (6 / 29) ** 2) + 4 / 29
