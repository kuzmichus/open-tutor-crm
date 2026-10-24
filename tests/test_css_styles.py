"""Тесты дизайн-системы: CSS не должен «молча» терять правила.

Нативный CSS не умеет конкатенировать селекторы через `&`: запись
`.block { &__el { ... } }` синтаксически валидна, но браузер выбрасывает
такое правило целиком. Внешне это выглядит как «стили не применились» —
именно из-за этого картинка на 404 раздувалась на весь экран.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
STYLES = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
TEMPLATES_DIR = ROOT / "app" / "templates"


def _without_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def test_no_bem_concatenation_nesting():
    """В CSS нет `&__x` / `&--x`: такой nesting браузер отбрасывает."""
    css = _without_comments(STYLES)
    offenders = re.findall(r"&(?:__|--)[\w-]+", css)
    assert not offenders, (
        "Нативный CSS не поддерживает конкатенацию селекторов через &. "
        "Перепишите правила плоскими BEM-селекторами: " + ", ".join(sorted(set(offenders)))
    )


def test_braces_are_balanced():
    css = _without_comments(STYLES)
    assert css.count("{") == css.count("}"), "Несбалансированные фигурные скобки в styles.css"


def test_404_art_is_bounded_in_width_and_height():
    """Иллюстрация 404 ограничена и по ширине, и по высоте."""
    block = re.search(r"\.not-found__art\s*\{([^}]*)\}", STYLES)
    assert block, "В styles.css нет правила .not-found__art"
    body = block.group(1)
    assert "max-width" in body, "У .not-found__art должен быть max-width"
    assert "height" in body, "У .not-found__art должна быть ограниченная высота"
    # height: auto + только width оставлял картинку без вертикального лимита.
    assert not re.search(r"height:\s*auto\s*;", body)


def _literal_classes(html: str) -> set[str]:
    """Литеральные классы из разметки.

    Alpine-привязки (`:class`, `x-bind:class`) и Jinja-выражения внутри
    атрибута — не имена классов, а значения, вычисляемые на клиенте или
    на сервере, поэтому в проверку они не попадают.
    """
    html = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", html, flags=re.S)
    used: set[str] = set()
    for attr in re.findall(r'(?<![:\w-])class="([^"]*)"', html):
        used.update(token for token in attr.split() if token)
    return used


# Каталоги шаблонов, чьи литеральные классы обязаны быть описаны в CSS
# (AGENTS.md: новый BEM-класс в шаблоне — с правилом в styles.css).
# `prefix` сужает проверку у общих шаблонов: 404.html и auth.html делят
# каталог с base.html и партиалами, чьи классы проверяются своими тестами.
TEMPLATE_SETS = [
    ("general-not-found", TEMPLATES_DIR, "not-found__", ("404.html",)),
    ("general-auth", TEMPLATES_DIR, "auth__", ("auth.html",)),
    (
        "student",
        ROOT / "app" / "student" / "templates" / "student",
        None,
        None,
    ),
    ("group", ROOT / "app" / "group" / "templates" / "group", None, None),
    ("finance", ROOT / "app" / "finance" / "templates" / "finance", None, None),
    ("slot", ROOT / "app" / "slot" / "templates" / "slot", None, None),
    ("booking", ROOT / "app" / "booking" / "templates" / "booking", None, None),
    (
        "unavailability",
        ROOT / "app" / "unavailability" / "templates" / "unavailability",
        None,
        None,
    ),
]

_TEMPLATE_CASES = [
    pytest.param(
        templates_dir,
        prefix,
        names or sorted(p.name for p in templates_dir.glob("*.html")),
        id=case_id,
    )
    for case_id, templates_dir, prefix, names in TEMPLATE_SETS
]


@pytest.mark.parametrize(("templates_dir", "prefix", "templates"), _TEMPLATE_CASES)
def test_template_classes_have_css_rules(templates_dir, prefix, templates):
    """Каждый литеральный BEM-класс из шаблона реально описан в styles.css."""
    for template in templates:
        html = (templates_dir / template).read_text(encoding="utf-8")
        used = _literal_classes(html)
        if prefix:
            used = {c for c in used if c.startswith(prefix)}
        missing = sorted(c for c in used if f".{c}" not in STYLES)
        assert not missing, f"{template}: классы без CSS-правил: {', '.join(missing)}"


def test_weekend_rules_are_removed_from_css():
    """Автоматической разметки выходных в CSS нет.

    Единственный источник выходных — отметки в таблице `tutor_unavailability`
    (спека calendar, «Выходные задаёт репетитор отметками»). Классы
    `.cal-day--weekend` / `.cal-dayhead--weekend` и токены `--cal-weekend` /
    `--cal-hatch` удалены вместе с плашкой «Выходной».
    """
    css = _without_comments(STYLES)
    for token in (
        "cal-day--weekend",
        "cal-dayhead--weekend",
        "--cal-weekend",
        "--cal-hatch",
    ):
        assert token not in css, f"в styles.css остался {token}"

    # Штриховка осталась только у отмеченного дня и опирается на --cal-off.
    block = re.search(r"\.cal-day--unavailable\s*\{(.*?)\n  \}", css, flags=re.S)
    assert block, "В styles.css нет правила .cal-day--unavailable"
    assert "--cal-off" in block.group(1)


def test_groups_grid_is_responsive():
    """Сетка групп: одна колонка на телефоне, больше — на широких экранах."""
    block = re.search(r"\.groups-grid\s*\{(.*?)\n  \}", STYLES, flags=re.S)
    assert block, "В styles.css нет правила .groups-grid"
    body = block.group(1)
    assert "grid-template-columns: 1fr" in body
    # Узкие экраны не ломают сетку: колонки добавляются только по min-width.
    assert "@media (min-width: 640px)" in body
    assert "@media (min-width: 1024px)" in body


def test_group_card_uses_theme_tokens():
    """Карточка группы не хардкодит цвета: только токены тёмной/светлой темы."""
    block = re.search(r"\.group-card\s*\{(.*?)\n  \}", STYLES, flags=re.S)
    assert block, "В styles.css нет правила .group-card"
    body = block.group(1)
    for prop in ("background: var(--card)", "color: var(--card-foreground)",
                 "border: 1px solid var(--border)"):
        assert prop in body, f".group-card без токена темы: {prop}"
    # Никаких литеральных цветов (#fff, rgb(...)) в карточке.
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", body)


def test_group_menu_is_styled():
    """Меню «...» карточки описано: кнопка, список, опасный пункт."""
    for selector in (
        ".group-card__menu",
        ".group-card__menu-list",
        ".group-card__menu-item",
        ".group-card__menu-item--danger",
    ):
        assert selector in STYLES, f"нет правила {selector}"
