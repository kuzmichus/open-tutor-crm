"""Тесты цвета события Google по цвету цели урока.

Проверяется чистая функция `event_color.color_id`: соответствие палитры
CRM палитре Google, ближайший цвет для незнакомого hex и безопасный
default для пустого значения. Сеть и БД не участвуют.
"""

import pytest

from app.common.colors import DEFAULT_TARGET_COLOR, PALETTE
from app.gcalendar.services.event_color import (
    DEFAULT_COLOR_ID,
    GOOGLE_EVENT_COLORS,
    PALETTE_COLOR_IDS,
    color_id,
)

# Ожидаемое соответствие: цвет CRM → colorId Google. Таблица продублирована
# в тесте намеренно — правка кода без правки ожиданий должна падать.
EXPECTED = {
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

def test_google_palette_has_eleven_event_colors():
    """Палитра событий Google — 11 цветов с hex-значениями."""
    assert len(GOOGLE_EVENT_COLORS) == 11
    assert set(GOOGLE_EVENT_COLORS) == {str(number) for number in range(1, 12)}
    for hex_color in GOOGLE_EVENT_COLORS.values():
        assert len(hex_color) == 7 and hex_color.startswith("#")

def test_every_crm_palette_color_is_mapped():
    """Каждый цвет палитры CRM и цвет по умолчанию есть в таблице."""
    assert set(PALETTE) <= set(PALETTE_COLOR_IDS)
    assert DEFAULT_TARGET_COLOR in PALETTE_COLOR_IDS

@pytest.mark.parametrize(("crm_color", "expected"), sorted(EXPECTED.items()))
def test_palette_color_maps_to_expected_google_color(crm_color, expected):
    """Цвет цели даёт заранее выбранный colorId Google."""
    assert color_id(crm_color) == expected

@pytest.mark.parametrize("crm_color", sorted(EXPECTED))
def test_result_is_always_a_google_color_id(crm_color):
    """Возвращается строка из набора «1»–«11», как ждёт Calendar API."""
    result = color_id(crm_color)
    assert isinstance(result, str)
    assert result in GOOGLE_EVENT_COLORS

def test_hex_case_and_spaces_do_not_matter():
    """Регистр hex и пробелы по краям не влияют на результат."""
    assert color_id("#DD3C3C") == color_id("#dd3c3c") == "11"
    assert color_id("  #dd3c3c ") == "11"

@pytest.mark.parametrize("empty", [None, "", "   "])
def test_empty_color_falls_back_to_default(empty):
    """Цвет не задан (NULL у старой записи) — цвет по умолчанию CRM."""
    assert color_id(empty) == DEFAULT_COLOR_ID == "9"

@pytest.mark.parametrize("broken", ["нет", "#12", "#1234567", "#zzzzzz", "3b82f6ff"])
def test_broken_color_falls_back_to_default(broken):
    """Некорректный hex не роняет синхронизацию: срабатывает default."""
    assert color_id(broken) == DEFAULT_COLOR_ID

def test_unknown_hex_gets_nearest_google_color():
    """Незнакомый, но валидный hex красится в ближайший цвет Google."""
    # Чистый красный ближе всего к Tomato, белый — к Graphite.
    assert color_id("#ff0000") == "11"
    assert color_id("#ffffff") == "8"

def test_default_crm_color_is_blueberry():
    """Цвет по умолчанию CRM ближе всего к Blueberry."""
    assert color_id(DEFAULT_TARGET_COLOR) == "9"
    assert GOOGLE_EVENT_COLORS["9"] == "#5484ed"
