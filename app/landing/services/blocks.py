"""Набор блоков GrapesJS для редактора лендинга.

Ядро GrapesJS 0.23.9 не содержит блоков: панель «Блоки» пуста, пока
приложение не зарегистрирует их через `blockManager`. Здесь описан набор,
из которого репетитор собирает страницу мышью.

Секции используют классы и CSS-переменные шаблона по умолчанию
(`default_page.html.j2`), поэтому вставленный блок сразу выглядит как
остальная страница и переживает сохранение: правила этих классов уже
лежат в первом `<style>` черновика. Служебные блоки без собственного
класса (разделитель, колонки) несут оформление в атрибуте `style` — так
они выглядят одинаково и в старом черновике, где новых правил в CSS ещё
нет.

CTA блока «Обложка» ведёт на публичную страницу записи текущего
репетитора: адрес `/s/<tutor_id>` знает только сервер, поэтому он
подставляется при рендере редактора, а не хранится в статическом JSON.

Подписи блоков и категорий живут в русской локали
(`app/static/dist/grapesjs/i18n-ru.js`): GrapesJS берёт их оттуда по id,
как и остальные строки интерфейса.
"""

from textwrap import dedent

# Категории в порядке показа в панели: сначала готовые секции лендинга,
# затем простые элементы и раскладка.
CATEGORY_LANDING = "landing"
CATEGORY_BASIC = "basic"
CATEGORY_LAYOUT = "layout"

BLOCK_CATEGORIES = (CATEGORY_LANDING, CATEGORY_BASIC, CATEGORY_LAYOUT)


def _html(markup: str) -> str:
    """HTML блока без отступов исходника: GrapesJS парсит строку как есть."""
    return dedent(markup).strip()


def _block(
    block_id: str,
    category: str,
    markup: str,
    **options: object,
) -> dict:
    """Описание одного блока GrapesJS: id, категория, содержимое, опции."""
    block: dict = {
        "id": block_id,
        "category": category,
        "content": _html(markup),
    }
    block.update(options)
    return block


def landing_blocks(cta_url: str) -> list[dict]:
    """Блоки редактора для этого репетитора.

    `cta_url` — адрес публичной страницы записи (`/s/<tutor_id>`): он
    попадает в ссылку блока «Обложка» и кнопки.
    """
    return [
        _block(
            "header",
            CATEGORY_LANDING,
            """
            <header class="header">
              <span class="header__name">Имя репетитора</span>
              <nav class="header__logins" aria-label="Вход в личный кабинет">
                <a class="login-link" href="/student/login" data-auth="student">Вход для ученика</a>
                <a class="login-link" href="/parent/login" data-auth="parent">Вход для родителя</a>
              </nav>
            </header>
            """,
        ),
        _block(
            "hero",
            CATEGORY_LANDING,
            f"""
            <section class="hero">
              <h1 class="hero__name">Имя репетитора</h1>
              <p class="hero__subject">Репетитор по предмету</p>
              <a class="cta" href="{cta_url}">Записаться на занятие</a>
              <p class="cta__hint">Выберите удобное время на странице записи</p>
            </section>
            """,
        ),
        _block(
            "about",
            CATEGORY_LANDING,
            """
            <section class="section">
              <h2 class="section__title">О себе</h2>
              <p class="section__text">Расскажите об опыте и подходе к занятиям.</p>
              <p class="section__meta">Опыт работы: 5 лет</p>
            </section>
            """,
        ),
        _block(
            "price",
            CATEGORY_LANDING,
            """
            <section class="section">
              <h2 class="section__title">Стоимость</h2>
              <div class="price">
                <span class="price__value">1 200 ₽</span>
                <span class="price__unit">за занятие</span>
              </div>
            </section>
            """,
        ),
        _block(
            "contacts",
            CATEGORY_LANDING,
            """
            <section class="section">
              <h2 class="section__title">Контакты</h2>
              <a class="contact-link" href="tel:+79991234567">+7 (999) 123-45-67</a>
            </section>
            """,
        ),
        _block(
            "footer",
            CATEGORY_LANDING,
            """
            <footer class="footer">
              <span>Имя репетитора</span>
              <a class="footer__login" href="/tutor/login" data-auth="tutor">вход</a>
            </footer>
            """,
        ),
        _block(
            "heading",
            CATEGORY_BASIC,
            '<h2 class="section__title">Заголовок</h2>',
        ),
        _block(
            "text",
            CATEGORY_BASIC,
            '<p class="section__text">Текст</p>',
        ),
        # Пустой `src` — осознанно: без него GrapesJS записал бы в HTML
        # служебную data-URI-заглушку, если картинку не выбрали. Маркер
        # `data-landing-image` ловит редактор и сразу открывает Asset
        # Manager; на сохранённой странице атрибута уже нет.
        _block(
            "image",
            CATEGORY_BASIC,
            '<img alt="Изображение" data-landing-image '
            'style="max-width: 100%; height: auto">',
        ),
        _block(
            "button",
            CATEGORY_BASIC,
            f'<a class="cta" href="{cta_url}">Кнопка</a>',
        ),
        _block(
            "divider",
            CATEGORY_BASIC,
            """
            <hr style="border: 0; border-top: 1px solid var(--border); margin: 32px 0">
            """,
        ),
        _block(
            "column2",
            CATEGORY_LAYOUT,
            """
            <div style="display: flex; gap: 24px; flex-wrap: wrap">
              <div style="flex: 1 1 240px">
                <p class="section__text">Колонка 1</p>
              </div>
              <div style="flex: 1 1 240px">
                <p class="section__text">Колонка 2</p>
              </div>
            </div>
            """,
        ),
        _block(
            "column3",
            CATEGORY_LAYOUT,
            """
            <div style="display: flex; gap: 24px; flex-wrap: wrap">
              <div style="flex: 1 1 180px">
                <p class="section__text">Колонка 1</p>
              </div>
              <div style="flex: 1 1 180px">
                <p class="section__text">Колонка 2</p>
              </div>
              <div style="flex: 1 1 180px">
                <p class="section__text">Колонка 3</p>
              </div>
            </div>
            """,
        ),
    ]
