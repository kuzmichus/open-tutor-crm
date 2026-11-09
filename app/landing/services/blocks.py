"""Набор блоков GrapesJS для редактора лендинга.

Ядро GrapesJS 0.23.9 не содержит блоков: панель «Блоки» пуста, пока
приложение не зарегистрирует их через `blockManager`. Здесь описан набор,
из которого репетитор собирает страницу мышью.

Разметка блоков живёт отдельными файлами в
`app/landing/templates/blocks/` — рядом с `default_page.html.j2`, чтобы
править дизайн страницы и блоков в одном месте. Сервис только собирает
набор: id, категория, отрендеренное содержимое файла.

Секции используют классы и CSS-переменные шаблона по умолчанию
(`default_page.html.j2`), поэтому вставленный блок сразу выглядит как
остальная страница и переживает сохранение: правила этих классов уже
лежат в первом `<style>` черновика. Набор секций повторяет структуру
шаблона по умолчанию: тот же порядок и та же разметка, но с
демо-текстами вместо данных профиля. Служебные блоки без собственного
класса (разделитель, колонки) несут оформление в атрибуте `style` — так
они выглядят одинаково и в старом черновике, где новых правил в CSS ещё
нет.

CTA блоков «Обложка», «Услуги и цены» и «Запись» ведут на публичную
страницу записи текущего репетитора: адрес `/s/<tutor_id>` знает только
сервер, поэтому он подставляется при рендере редактора, а не хранится в
статическом JSON.

Подписи блоков и категорий живут в русской локали
(`app/static/dist/grapesjs/i18n-ru.js`): GrapesJS берёт их оттуда по id,
как и остальные строки интерфейса.
"""

# Категории в порядке показа в панели: сначала готовые секции лендинга,
# затем простые элементы и раскладка.
CATEGORY_LANDING = "landing"
CATEGORY_BASIC = "basic"
CATEGORY_LAYOUT = "layout"

BLOCK_CATEGORIES = (CATEGORY_LANDING, CATEGORY_BASIC, CATEGORY_LAYOUT)

# (id блока, категория, имя файла разметки в `templates/blocks/`). Порядок
# кортежа — порядок показа в панели блоков: секции идут в том же порядке,
# что и на странице по умолчанию. id `price` сохранён за секцией «Услуги и
# цены» (раньше там была одна ставка) — подпись живёт в русской локали.
BLOCK_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("header", CATEGORY_LANDING, "header.html.j2"),
    ("hero", CATEGORY_LANDING, "hero.html.j2"),
    ("price", CATEGORY_LANDING, "price.html.j2"),
    ("about", CATEGORY_LANDING, "about.html.j2"),
    ("education", CATEGORY_LANDING, "education.html.j2"),
    ("reviews", CATEGORY_LANDING, "reviews.html.j2"),
    ("steps", CATEGORY_LANDING, "steps.html.j2"),
    ("faq", CATEGORY_LANDING, "faq.html.j2"),
    ("signup", CATEGORY_LANDING, "signup.html.j2"),
    ("contacts", CATEGORY_LANDING, "contacts.html.j2"),
    ("footer", CATEGORY_LANDING, "footer.html.j2"),
    ("heading", CATEGORY_BASIC, "heading.html.j2"),
    ("text", CATEGORY_BASIC, "text.html.j2"),
    ("image", CATEGORY_BASIC, "image.html.j2"),
    ("button", CATEGORY_BASIC, "button.html.j2"),
    ("divider", CATEGORY_BASIC, "divider.html.j2"),
    ("column2", CATEGORY_LAYOUT, "column2.html.j2"),
    ("column3", CATEGORY_LAYOUT, "column3.html.j2"),
)


def landing_blocks(cta_url: str) -> list[dict]:
    """Блоки редактора для этого репетитора.

    `cta_url` — адрес публичной страницы записи (`/s/<tutor_id>`): он
    попадает в ссылку блока «Обложка» и кнопки. Содержимое берётся из
    файлов разметки и `.strip()`-ится: у блока не должно быть ни ведущего
    перевода строки от комментария файла, ни хвостового — GrapesJS парсит
    строку как есть.
    """
    from app.templating import templates

    blocks: list[dict] = []
    for block_id, category, template_name in BLOCK_TEMPLATES:
        content = templates.env.get_template(f"blocks/{template_name}")
        blocks.append(
            {
                "id": block_id,
                "category": category,
                "content": content.render(cta_url=cta_url).strip(),
            }
        )
    return blocks
