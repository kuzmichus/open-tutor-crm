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


@pytest.mark.parametrize("template", ["404.html", "auth.html"])
def test_template_classes_have_css_rules(template: str):
    """Каждый BEM-класс из шаблона реально описан в styles.css."""
    path = TEMPLATES_DIR / template
    if not path.exists():
        pytest.skip(f"{template} отсутствует")
    html = path.read_text(encoding="utf-8")
    prefix = "auth__" if template == "auth.html" else "not-found__"
    used = {c for c in re.findall(rf'class="([^"]+)"', html) for c in c.split()}
    used = {c for c in used if c.startswith(prefix)}
    missing = sorted(c for c in used if f".{c}" not in STYLES)
    assert not missing, f"Классы без CSS-правил: {', '.join(missing)}"


STUDENT_TEMPLATES_DIR = ROOT / "app" / "student" / "templates" / "student"


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


@pytest.mark.parametrize(
    "template",
    sorted(p.name for p in STUDENT_TEMPLATES_DIR.glob("*.html")),
)
def test_student_template_classes_have_css_rules(template: str):
    """Каждый класс из шаблонов учеников описан в styles.css."""
    html = (STUDENT_TEMPLATES_DIR / template).read_text(encoding="utf-8")
    missing = sorted(c for c in _literal_classes(html) if f".{c}" not in STYLES)
    assert not missing, (
        f"{template}: классы без CSS-правил: {', '.join(missing)}"
    )
