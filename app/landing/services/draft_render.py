"""Разбор черновика лендинга и сборка полного HTML-документа.

Формат `draft.html` контролирует только наш код: файл пишет шаблон по
умолчанию (`template.py`) и редактор (через `build_document`), поэтому
разбор идёт простыми регулярками, без HTML-парсера и без зависимостей.
Модуль не знает про FastAPI и ничего не читает с диска — на вход приходят
строки, на выходе тоже строка.

Зачем разбирать и собирать заново: GrapesJS работает с фрагментом `<body>`
и CSS отдельно (`getHtml()` / `getCss()`), а на диске лежит полноценный
документ. При загрузке редактора из документа извлекаются тело и первый
`<style>`; при сохранении тело и CSS снова оборачиваются в фиксированную
шапку. `<title>` переносится из текущего черновика, чтобы правка тела не
сбрасывала заголовок страницы.

Тег `<script src="/static/landing-auth.js" defer></script>` — часть
опубликованной страницы (подмена кнопок входа), но не часть редактируемого
контента: GrapesJS вырезал бы скрипт из тела. Поэтому при сохранении тег
идемпотентно гарантируется в конце документа: маркер уже есть — документ
не меняется, иначе тег вставляется перед `</body>`.
"""

import html
import re

# Тег подмены входов на опубликованной странице и его маркер. Проверка
# идёт по маркеру, а не по полному тегу: старый черновик мог содержать
# другой порядок атрибутов, и второй тег не нужен.
AUTH_SCRIPT = '<script src="/static/landing-auth.js" defer></script>'
AUTH_MARKER = "landing-auth.js"

_BODY_RE = re.compile(r"<body\b[^>]*>(.*?)</body\s*>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title\s*>", re.IGNORECASE | re.DOTALL)
# Самозакрывающийся <script ... /> и обычный <script ...>...</script>.
_SCRIPT_RE = re.compile(
    r"<script\b[^>]*/>|<script\b[^>]*>.*?</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_BODY_END_RE = re.compile(r"</body\s*>", re.IGNORECASE)

# Блок объявлений без вложенных блоков: так обрабатываются и обычные правила,
# и содержимое `@media` (внешние фигурные скобки содержат вложенные и в шаблон
# не попадают).
_DECL_BLOCK_RE = re.compile(r"\{([^{}]*)\}")
_DECLARATION_RE = re.compile(r"^\s*([-\w]+)\s*:\s*(.*?)\s*$", re.DOTALL)

_BOX_SIDES = ("top", "right", "bottom", "left")
_BORDER_SIDES = ("top", "right", "bottom", "left")
_BORDER_STYLES = {
    "none",
    "hidden",
    "dotted",
    "dashed",
    "solid",
    "double",
    "groove",
    "ridge",
    "inset",
    "outset",
}
_BORDER_INITIAL = {"width": "medium", "style": "none", "color": "currentcolor"}
_RADIUS_CORNERS = (
    "top-left",
    "top-right",
    "bottom-right",
    "bottom-left",
)


def extract_body(document: str) -> str:
    """Содержимое первого `<body>` без самого тега; тела нет — пустая строка."""
    match = _BODY_RE.search(document)
    return match.group(1) if match else ""


def extract_first_style(document: str) -> str:
    """Содержимое первого `<style>`; остальные блоки игнорируются."""
    match = _STYLE_RE.search(document)
    return match.group(1) if match else ""


def extract_title(document: str) -> str | None:
    """Заголовок из первого `<title>`; пустой заголовок — как отсутствующий."""
    match = _TITLE_RE.search(document)
    if match is None:
        return None
    title = match.group(1).strip()
    return title or None


def strip_scripts(fragment: str) -> str:
    """Удаляет `<script>` из фрагмента, загружаемого в редактор.

    Скрипты в теле не редактируются: GrapesJS всё равно вырезал бы их, а
    `landing-auth.js` добавляется при сохранении отдельно. Функция
    применяется только к телу, не к собранному документу.
    """
    return _SCRIPT_RE.sub("", fragment)


def _split_css_values(value: str) -> list[str]:
    """Делит значение по пробелам, не трогая пробелы внутри `var(...)`."""
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _box_values(values: list[str]) -> list[str]:
    """Приводит 1–4 значения `margin`/`padding` к порядку top/right/bottom/left."""
    if len(values) == 1:
        return values * 4
    if len(values) == 2:
        return [values[0], values[1], values[0], values[1]]
    if len(values) == 3:
        return [values[0], values[1], values[2], values[1]]
    if len(values) == 4:
        return values
    return []


def _expand_box_shorthand(prop: str, value: str) -> list[tuple[str, str]] | None:
    """`margin`/`padding` с `var()` → четыре длинных свойства."""
    sides = _box_values(_split_css_values(value))
    if not sides:
        return None
    return [
        (f"{prop}-{side}", side_value) for side, side_value in zip(_BOX_SIDES, sides, strict=True)
    ]


def _is_length(token: str) -> bool:
    """Толщина рамки: число с единицей или ключевое слово."""
    return bool(re.fullmatch(r"[+-]?(?:\d*\.)?\d+[a-z%]*", token)) or token in {
        "thin",
        "medium",
        "thick",
    }


def _expand_border_shorthand(prop: str, value: str) -> list[tuple[str, str]] | None:
    """`border`/`border-*` с `var()` → ширина, стиль и цвет каждой стороны.

    CSSOM (а значит и парсер GrapesJS) не умеет разобрать сокращение, если
    хотя бы одна его часть задана через `var()`, и молча выбрасывает всё
    объявление. Длинные свойства с `var()` он сохраняет.
    """
    sides = _BORDER_SIDES if prop == "border" else (prop.split("-", 1)[1],)
    kinds: dict[str, str] = {}
    variables: list[str] = []
    for token in _split_css_values(value):
        lowered = token.lower()
        if lowered.startswith("var("):
            variables.append(token)
        elif lowered in _BORDER_STYLES:
            kinds.setdefault("style", token)
        elif _is_length(lowered):
            kinds.setdefault("width", token)
        else:
            kinds.setdefault("color", token)
    # Недостающие части сокращения заполняем `var()` в порядке CSS
    # (ширина, стиль, цвет): в шаблоне это `border: 1px solid var(--border)`.
    missing = [key for key in ("width", "style", "color") if key not in kinds]
    for key, token in zip(missing, variables, strict=False):
        kinds[key] = token
    if not kinds:
        return None
    return [
        (f"border-{side}-{part}", kinds.get(part, initial))
        for side in sides
        for part, initial in _BORDER_INITIAL.items()
    ]


def _expand_radius_shorthand(value: str) -> list[tuple[str, str]] | None:
    """`border-radius` с `var()` → четыре угла (эллипсы не поддерживаем)."""
    if "/" in value:
        return None
    values = _split_css_values(value)
    if not 1 <= len(values) <= 4:
        return None
    if len(values) == 1:
        values = values * 4
    elif len(values) == 2:
        values = [values[0], values[1], values[0], values[1]]
    elif len(values) == 3:
        values = [values[0], values[1], values[2], values[1]]
    return [
        (f"border-{corner}-radius", corner_value)
        for corner, corner_value in zip(_RADIUS_CORNERS, values, strict=True)
    ]


def _expand_gap_shorthand(value: str) -> list[tuple[str, str]] | None:
    values = _split_css_values(value)
    if len(values) == 1:
        return [("row-gap", values[0]), ("column-gap", values[0])]
    if len(values) == 2:
        return [("row-gap", values[0]), ("column-gap", values[1])]
    return None


def _expand_background_shorthand(value: str) -> list[tuple[str, str]] | None:
    """`background: var(--x)` → `background-color` (в шаблоне это цвет)."""
    values = _split_css_values(value)
    if len(values) == 1 and values[0].lower().startswith("var("):
        return [("background-color", values[0])]
    return None


def _expand_declaration(prop: str, value: str) -> list[tuple[str, str]] | None:
    """Длинные свойства для сокращения с `var()`; `None` — оставить как есть."""
    if "var(" not in value:
        return None
    if prop in ("margin", "padding"):
        return _expand_box_shorthand(prop, value)
    if prop == "border" or prop in {
        "border-top",
        "border-right",
        "border-bottom",
        "border-left",
    }:
        return _expand_border_shorthand(prop, value)
    if prop == "border-radius":
        return _expand_radius_shorthand(value)
    if prop == "gap":
        return _expand_gap_shorthand(value)
    if prop == "background":
        return _expand_background_shorthand(value)
    return None


def _expand_block(block: str) -> str:
    """Переписывает объявления одного блока, остальные оставляет дословно."""
    declarations: list[str] = []
    for part in block.split(";"):
        match = _DECLARATION_RE.match(part)
        if match is None:
            declarations.append(part)
            continue
        prop, value = match.group(1).lower(), match.group(2)
        expanded = _expand_declaration(prop, value)
        if expanded is None:
            declarations.append(part)
            continue
        declarations.extend(f"{name}: {expanded_value}" for name, expanded_value in expanded)
    return "{" + ";".join(declarations) + "}"


def css_for_editor(css: str) -> str:
    """Готовит CSS черновика к загрузке в GrapesJS без потери оформления.

    GrapesJS разбирает стили браузерным CSSOM, а тот выбрасывает сокращённые
    свойства, если их часть задана через `var()`: `background: var(--bg)`,
    `border: 1px solid var(--border)`, `border-radius: var(--radius)`.
    После сохранения такие объявления исчезали, и страница теряла цвет CTA и
    рамки. Здесь сокращения с `var()` заранее разворачиваются в эквивалентные
    длинные свойства — их CSSOM сохраняет, а оформление не меняется.
    """
    return _DECL_BLOCK_RE.sub(lambda match: _expand_block(match.group(1)), css)


def default_title(tutor) -> str:
    """`<title>` по умолчанию: «{имя} — репетитор», безопасный для HTML.

    Имя экранируется без кавычек: оно попадает в текстовый узел `<title>`,
    а не в атрибут. Пустое имя даёт «— репетитор» — это тот же формат,
    что у шаблона по умолчанию.
    """
    name = (tutor.name or "").strip()
    return html.escape(f"{name} — репетитор", quote=False)


def build_document(*, body: str, css: str, title: str) -> str:
    """Собирает полный документ из тела, CSS и готового `<title>`.

    `title` вставляется как уже готовый HTML: из черновика он берётся
    как есть, а `default_title` экранирует имя заранее. Повторное
    экранирование сломало бы сущности вроде `&amp;`.
    """
    return (
        "<!doctype html>\n"
        '<html lang="ru">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f"<style>{css}</style>\n"
        "</head>\n"
        f"<body>{body}</body>\n"
        "</html>\n"
    )


def ensure_auth_script(document: str) -> str:
    """Гарантирует ровно один тег `landing-auth.js` перед `</body>`.

    Идемпотентна: если маркер уже встречается в документе, строка
    возвращается без изменений. Без `</body>` (испорченный/фрагментный
    документ) тег дописывается в конец.
    """
    if AUTH_MARKER in document:
        return document
    matches = list(_BODY_END_RE.finditer(document))
    if not matches:
        return document + AUTH_SCRIPT
    end = matches[-1]
    return document[: end.start()] + AUTH_SCRIPT + document[end.start() :]


def render_draft_document(
    tutor,
    *,
    html: str,
    css: str,
    existing_html: str | None = None,
) -> str:
    """Собирает итоговый `draft.html` для сохранения из редактора.

    `html` — содержимое тела от `editor.getHtml()`, `css` — от
    `editor.getCss()`. Заголовок берётся из текущего черновика, чтобы
    правка не сбрасывала `<title>`; если черновика нет или заголовок
    пуст — подставляется «{имя} — репетитор».

    `editor.getHtml()` возвращает компонент-обёртку `<body>…</body>`
    (GrapesJS всегда оборачивает компоненты в body). Обёртка снимается,
    иначе при повторном открытии получился бы `<body>` внутри `<body>`.
    """
    body = html
    body_match = _BODY_RE.search(html)
    if body_match is not None:
        body = body_match.group(1)
    title = extract_title(existing_html) if existing_html else None
    if title is None:
        title = default_title(tutor)
    return ensure_auth_script(build_document(body=body, css=css, title=title))
