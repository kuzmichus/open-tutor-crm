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
