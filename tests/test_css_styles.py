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


def test_fonts_are_local_not_cdn():
    """Шрифты лежат в проекте, а не тянутся с CDN (правило AGENTS.md п. 8).

    Кабинет работает на своём сервере: недоступный fonts.googleapis.com —
    это подмена гарнитуры на системную и внешний запрос на каждой странице.
    Поэтому `@font-face` объявлен в `styles.css`, файлы — в `static/fonts/`,
    а в шаблонах нет ссылок на Google Fonts.
    """
    templates = list((ROOT / "app").rglob("*.html"))
    assert templates
    for path in templates:
        # Jinja-комментарии вырезаем: пояснение «почему без CDN» само
        # содержит имя хоста, и проверка ловила бы текст, а не ссылку.
        markup = re.sub(r"\{#.*?#\}", "", path.read_text(encoding="utf-8"), flags=re.S)
        assert "fonts.googleapis.com" not in markup, f"{path}: ссылка на CDN"
        assert "fonts.gstatic.com" not in markup, f"{path}: ссылка на CDN"

    faces = re.findall(r"@font-face \{(.*?)\}", STYLES, flags=re.S)
    assert faces, "в styles.css нет @font-face"

    for body in faces:
        src = re.search(r'src: url\("([^"]+)"\)', body)
        assert src, body
        assert src.group(1).startswith("/static/fonts/"), (
            f"шрифт должен отдаваться локально: {src.group(1)}"
        )
        font_file = STATIC_DIR / src.group(1).removeprefix("/static/")
        assert font_file.is_file(), f"нет файла шрифта: {src.group(1)}"
        # Вариативные файлы: диапазон веса закрывает все начертания макета
        # (400/500/600/700) одним файлом вместо четырёх копий.
        assert "font-weight: 100 900" in body, body
        assert "font-display: swap" in body, body

    # Все три гарнитуры дизайн-системы объявлены локально.
    for family in ("Geist", "Geist Mono", "Lexend"):
        assert f'font-family: "{family}"' in STYLES, f"нет @font-face для {family}"


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
    ("lesson", ROOT / "app" / "lesson" / "templates" / "lesson", None, None),
    ("finance", ROOT / "app" / "finance" / "templates" / "finance", None, None),
    ("tutor", ROOT / "app" / "tutor" / "templates" / "tutor", None, None),
    ("slot", ROOT / "app" / "slot" / "templates" / "slot", None, None),
    ("booking", ROOT / "app" / "booking" / "templates" / "booking", None, None),
    (
        "unavailability",
        ROOT / "app" / "unavailability" / "templates" / "unavailability",
        None,
        None,
    ),
    ("stats", ROOT / "app" / "stats" / "templates" / "stats", None, None),
    ("task", ROOT / "app" / "task" / "templates" / "task", None, None),
    ("mailing", ROOT / "app" / "mailing" / "templates" / "mailing", None, None),
    (
        "cabinet",
        ROOT / "app" / "cabinet" / "templates" / "cabinet",
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


def test_no_color_literals_outside_tokens():
    """Цвета живут только в `@layer tokens`, не в правилах компонентов.

    Литерал в компоненте не переопределяется тёмной темой: `#ef4444` в
    рамке просроченного урока оставался ярко-красным на тёмном фоне, а
    белая подпись на `.btn--brand` давала в тёмной теме 3.29:1. Токены
    держат такие цвета рядом и позволяют теме их переопределить.
    """
    lines = STYLES.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("@layer tokens"))
    end = next(i for i, line in enumerate(lines) if line.startswith("@layer base"))

    pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)|\bhsla?\([^)]*\)")
    offenders = []
    for number, line in enumerate(lines, 1):
        if start < number <= end:
            continue
        stripped = line.lstrip()
        # Комментарии и `@font-face` (там нет цветов, но есть `unicode-range`)
        # не проверяем: это не правила оформления.
        if stripped.startswith("/*") or stripped.startswith("*"):
            continue
        for literal in pattern.findall(line):
            offenders.append(f"{number}: {literal} — {stripped[:60]}")

    assert not offenders, "цветовые литералы вне @layer tokens: " + "; ".join(
        offenders
    )


def _token_block(name: str) -> str:
    """Тело блока токенов: `:root` (светлая база) или `.dark`.

    Ищем по имени селектора на границе строки: `:root` встречается ещё и
    внутри `@layer tokens`, а `.dark` — только один раз.
    """
    match = re.search(
        r"(?:^|\n)\s*" + re.escape(name) + r"\s*\{(.*?)\n  \}",
        _without_comments(STYLES),
        flags=re.S,
    )
    assert match, f"в styles.css нет блока токенов {name}"
    return match.group(1)


def _tokens(name: str) -> dict[str, str]:
    """Плоский словарь `--токен` → значение из блока токенов.

    Значение берётся сырым: у статусов тёмной темы фон задан полупрозрачным
    `rgba(...)`, и разрешать его в цвет нужно на фоне карточки — см.
    `_resolve`.
    """
    return dict(
        re.findall(
            r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{6}\b|rgba?\([^)]*\))",
            _token_block(name),
        )
    )


def _channels(value: int) -> float:
    srgb = value / 255
    return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4


def _luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126 * _channels(r) + 0.7152 * _channels(g) + 0.0722 * _channels(b)


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.strip()
    if value.startswith("#"):
        digits = value.lstrip("#")
        return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    red, green, blue = (int(part) for part in value[value.index("(") + 1 : value.index(")")].split(",")[:3])
    return red, green, blue


def _alpha(value: str) -> float:
    if not value.strip().startswith("rgba"):
        return 1.0
    return float(value[value.index("(") + 1 : value.index(")")].split(",")[3])


def _resolve(tokens: dict[str, str], token: str) -> tuple[float, float, float]:
    """Цвет токена «как его увидит глаз» — с учётом прозрачности.

    Полупрозрачный тинт (фон статуса в тёмной теме) сам по себе цвета не
    имеет: он ложится на карточку. Композитим по альфе над `--card`,
    иначе сравнение шло бы с несуществующим цветом.
    """
    value = tokens[token]
    alpha = _alpha(value)
    red, green, blue = _rgb(value)
    if alpha >= 1:
        return float(red), float(green), float(blue)
    base = _rgb(tokens["--card"])
    return tuple(  # type: ignore[return-value]
        alpha * channel + (1 - alpha) * under
        for channel, under in zip((red, green, blue), base)
    )


def _contrast(tokens: dict[str, str], foreground: str, background: str) -> float:
    first = _luminance(_resolve(tokens, foreground))
    second = _luminance(_resolve(tokens, background))
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


# Пары «цвет текста → фоны, на которых он реально встречается». Это не
# гипотеза: `--muted-foreground` — заголовки таблиц и неактивные табы,
# `--success`/`--destructive` — суммы и метки долга, `--brand` — ссылки и
# аватар на `--brand-soft`. Все они мелкий текст (< 18.66px), поэтому
# норма AA — 4.5:1, а не 3:1.
_TEXT_PAIRS = {
    "--muted-foreground": ("--background", "--card", "--surface", "--muted", "--brand-soft"),
    "--success": ("--background", "--card", "--surface", "--muted"),
    "--destructive": ("--background", "--card", "--surface", "--muted"),
    "--brand": ("--background", "--card", "--surface", "--muted", "--brand-soft"),
    "--warning-fg": ("--warning-soft",),
    "--status-cancelled-fg": ("--status-cancelled",),
    "--status-unplanned-fg": ("--status-unplanned",),
    "--status-rescheduled-fg": ("--status-rescheduled",),
    "--status-regular-fg": ("--status-regular",),
}

# Пары «подпись → заливка своей кнопки»: белый (или инверсный) текст на
# плотной плашке. Проверяются отдельно, потому что здесь норма считается
# от собственного фона токена, а не от фона страницы.
_FILL_PAIRS = {
    "--primary-foreground": "--primary",
    "--success-foreground": "--success",
    "--destructive-foreground": "--destructive",
    # Подпись на брендовой заливке: белый литерал в правиле `.btn--brand`
    # давал в тёмной теме 3.29:1 — бренд там светлее. Теперь цвет приходит
    # из токена, и пара проверяется как остальные кнопки.
    "--brand-foreground": "--brand",
}

_AA_SMALL_TEXT = 4.5


@pytest.mark.parametrize("theme", ["root", "dark"])
@pytest.mark.parametrize(
    ("foreground", "background"),
    [(fg, bg) for fg, bgs in _TEXT_PAIRS.items() for bg in bgs],
)
def test_text_tokens_pass_wcag_aa(theme, foreground, background):
    """Токены текста проходят AA на тех фонах, где они работают.

    Контраст — не вкусовщина, а несущая конструкция: у денег и статусов
    цвет единственный носитель смысла (зелёный плюс, красный долг).
    Половина нарушений прошлого аудита была не в компонентах, а в трёх
    токенах, которые подбирались «на глаз»: `--muted-foreground` давал
    4.19:1 на `--muted`, `--success` — 4.14:1, `--destructive` — 4.38:1.
    """
    tokens = _tokens(":root" if theme == "root" else ".dark")
    assert foreground in tokens, f"{theme}: нет токена {foreground}"
    assert background in tokens, f"{theme}: нет токена {background}"
    ratio = _contrast(tokens, foreground, background)
    assert ratio >= _AA_SMALL_TEXT, (
        f"{theme}: {foreground} {tokens[foreground]} на {background} "
        f"{tokens[background]} = {ratio:.2f}:1 — ниже AA ({_AA_SMALL_TEXT})"
    )


@pytest.mark.parametrize("theme", ["root", "dark"])
@pytest.mark.parametrize(
    ("foreground", "background"), sorted(_FILL_PAIRS.items())
)
def test_button_labels_pass_wcag_aa(theme, foreground, background):
    """Подпись на плотной заливке кнопки читается: 4.5:1 к своему фону."""
    tokens = _tokens(":root" if theme == "root" else ".dark")
    assert foreground in tokens, f"{theme}: нет токена {foreground}"
    assert background in tokens, f"{theme}: нет токена {background}"
    ratio = _contrast(tokens, foreground, background)
    assert ratio >= _AA_SMALL_TEXT, (
        f"{theme}: {foreground} на {background} = {ratio:.2f}:1 — ниже AA"
    )


def test_rating_stars_fill_up_to_selected():
    """Звёзды оценки заливаются «от начала»: выбранная и все до неё.

    `+` красит только соседа справа, поэтому правило обязано ловить
    предыдущие звёзды через `:has(~ …)`; кнопка сброса (`value=""`)
    в заливку никого включать не должна.
    """
    assert ".rating-star:has(> input:checked) .rating-star__view" in STYLES
    assert (
        '.rating-star:has(~ .rating-star > input:checked:not([value=""])) '
        ".rating-star__view"
    ) in STYLES


def _mobile_tap_block() -> str:
    """Тело мобильного блока тап-таргетов из styles.css."""
    match = re.search(
        r"@media \(max-width: 1023\.98px\)\s*\{\s*/\* `\.btn--icon`.*?\n  \}",
        STYLES,
        flags=re.S,
    )
    assert match, "в styles.css нет мобильного блока тап-таргетов"
    return match.group(0)


def test_mobile_tap_targets_are_44px():
    """WCAG 2.5.5: на телефоне цель для пальца не меньше 44×44.

    Кнопки кабинета — 36px, иконочные и пилюли — 32px, крестик баннера —
    24px. На десктопе плотность важна, поэтому размеры поднимаются только
    в мобильной раскладке; `min-height`/`min-width` перебивают конкретные
    `width`/`height` у модификаторов.
    """
    block = _mobile_tap_block()
    assert "min-height: 44px" in block
    assert "min-width: 44px" in block
    for selector in (
        ".btn,",
        ".btn--sm,",
        ".tab,",
        ".group-card__menu-item,",
        ".task-card__menu-item",
    ):
        assert selector in block, f"нет цели {selector} в мобильном блоке"
    # Текстовые вводы и селекты — тоже цель: 36px мало.
    assert ".input:not(textarea)" in block
    assert "height: 44px" in block
    # Крестик баннера: цель больше, но плашка не раздувается — отступы
    # отрицательные.
    assert ".notice-banner__close {" in block
    assert "margin: calc(var(--space) * -2)" in block


def test_mobile_sidebar_toggle_is_hidden_with_closed_sidebar():
    """Скрытая панель не оставляет на экране 11px кружка сворачивания.

    Кнопка вылезает за край сайдбара на отрицательном `right`: у уехавшей
    панели её остаток попадал в область экрана как цель без действия.
    """
    block = _mobile_tap_block()
    assert ".sidebar:not(.is-open) .sidebar__toggle" in block
    assert "display: none" in block
    # Размер цели поднят до 44, а вылет увеличен, чтобы кружок не наезжал
    # на содержимое страницы.
    assert "width: 44px" in block
    assert "right: -22px" in block


def test_desktop_density_is_untouched():
    """Плотность десктопа не поехала: базовые размеры остались прежними."""
    btn = re.search(r"\n  \.btn \{(.*?)\n  \}", STYLES, flags=re.S)
    assert btn, "нет правила .btn"
    assert "min-height: 36px" in btn.group(1)
    assert "min-width: 36px" in btn.group(1)
    icon = re.search(r"\n  \.btn--icon \{(.*?)\n  \}", STYLES, flags=re.S)
    assert icon, "нет правила .btn--icon"
    assert "width: 32px" in icon.group(1)


def test_lessons_table_density_is_desktop_first():
    """Таблица уроков не раздувается на десктопе ради мобильных целей.

    Цель чекбокса 44×44 в базовом правиле поднимала шапку с 42 до 60px:
    одна ячейка выбора задавала высоту всей строки заголовков (проверено
    в браузере). Поэтому 44×44 живёт в мобильном медиа-запросе, а базовое
    правило задаёт только выравнивание.

    `vertical-align: middle` у ссылки сортировки обязателен по той же
    причине: `inline-flex` по умолчанию встаёт на базовую линию, и под ним
    остаётся место под descender.
    """
    base_hit = re.search(r"\n  \.lessons-select-hit \{(.*?)\n  \}", STYLES, flags=re.S)
    assert base_hit, "нет базового правила .lessons-select-hit"
    assert "width: 44px" not in base_hit.group(1)
    assert "height: 44px" not in base_hit.group(1)

    sort_link = re.search(r"\n  \.lessons-table__sort \{(.*?)\n  \}", STYLES, flags=re.S)
    assert sort_link, "нет правила .lessons-table__sort"
    assert "vertical-align: middle" in sort_link.group(1)

    block = _mobile_tap_block()
    assert ".lessons-select-hit {" in block
    assert "width: 44px" in block
    assert "height: 44px" in block
