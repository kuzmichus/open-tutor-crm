"""Накладные выпадающие списки выбора.

Раскрытый список (ученик в форме урока, контакт, участник группы, часовой
пояс) должен накрывать соседние поля, а не раздвигать форму. Поэтому список
позиционируется `fixed` под полем (`app/static/dropdown.js`), а в CSS
`position: absolute` остаётся фолбэком до инициализации.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
BASE_HTML = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
STYLES = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
DROPDOWN_JS = (STATIC_DIR / "dropdown.js").read_text(encoding="utf-8")
PICKER_JS = (STATIC_DIR / "picker.js").read_text(encoding="utf-8")
COMBOBOX_JS = (STATIC_DIR / "combobox.js").read_text(encoding="utf-8")
LESSONS_JS = (STATIC_DIR / "lessons.js").read_text(encoding="utf-8")


def test_dropdown_js_is_served(client):
    response = client.get("/static/dropdown.js")
    assert response.status_code == 200
    assert "openDropdown" in response.text


def test_dropdown_js_loads_before_alpine():
    """Скрипт подключается вместе с остальными фабриками — до Alpine."""
    assert "/static/dropdown.js" in BASE_HTML
    assert BASE_HTML.index("dropdown.js") < BASE_HTML.index("alpine.min.js")


def test_list_is_positioned_over_layout():
    """Список вынесен из потока и лежит поверх полей."""
    start = STYLES.index(".combobox__list {")
    rule = STYLES[start : STYLES.index("}", start)]
    assert "position: absolute" in rule
    assert "z-index:" in rule
    # Высота списка больше не занимает место в сетке формы.
    assert "margin:" not in rule


def test_each_picker_uses_shared_positioning():
    """Три вида списков позиционируются одним хелпером, а не каждый сам."""
    for source in (PICKER_JS, COMBOBOX_JS, LESSONS_JS):
        assert "window.openDropdown" in source
        assert "window.closeDropdown" in source
    # Позиция пересчитывается при прокрутке/ресайзе и после htmx-свопа.
    assert 'addEventListener("scroll"' in DROPDOWN_JS
    assert 'addEventListener("resize"' in DROPDOWN_JS
    assert "htmx:afterSettle" in DROPDOWN_JS
