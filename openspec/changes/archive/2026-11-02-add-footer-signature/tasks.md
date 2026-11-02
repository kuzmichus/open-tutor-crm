# Tasks

## 1. Источник данных подписи

- [x] 1.1 `app/__init__.py`: рядом с `__version__` добавить константу
  `__repository_url__ = "https://github.com/kuzmichus/open-tutor-crm/"`.
  Проверка: `tests/test_footer_signature.py::test_version_and_repository_come_from_manifest_and_code`.
- [x] 1.2 `app/templating.py`: зарегистрировать в `templates.env.globals`
  переменные `app_version` (из `app.__version__`) и `app_repository_url` (из
  `app.__repository_url__`). Проверка: подпись на `/tutor/login` содержит
  текущую версию манифеста.

## 2. Разметка подписи

- [x] 2.1 `app/templates/_footer_signature.html`: версия `v{{ app_version }}`
  и ссылка `{{ app_repository_url }}` c `target="_blank"`,
  `rel="noopener noreferrer"` и `aria-label`, внутри — inline-SVG значка GitHub
  (`aria-hidden="true"`, `fill="currentColor"`). Проверка:
  `::test_tutor_footer_links_to_github_with_mark`.
- [x] 2.2 Включить партиал в подвал сайдбара репетитора
  (`app/templates/sidebar.html`) — после строки пользователя и формы выхода.
  Проверка: `::test_tutor_sidebar_footer_shows_current_version`,
  `::test_footer_signature_is_near_the_footer_end`.
- [x] 2.3 Включить партиал в подвалы кабинетов ученика и родителя
  (`app/cabinet/templates/cabinet/_sidebar.html`,
  `app/cabinet/templates/cabinet/parent/_sidebar.html`). Проверка:
  `::test_cabinet_sidebar_shows_signature`.
- [x] 2.4 Включить партиал на страницы входа/регистрации репетитора
  (`app/templates/auth.html`) — под карточкой формы, в обёртке `.auth__stack`.
- [x] 2.5 Включить партиал на страницы входа кабинетов
  (`app/cabinet/templates/cabinet/base.html`) — блок `.cabinet__signature`.
- [x] 2.6 Включить партиал на 404 (`app/templates/404.html`) — после кнопок.
  Проверка: `::test_404_page_shows_signature`,
  `::test_public_pages_show_signature` (четыре поверхности до входа).

## 3. Стили

- [x] 3.1 `app/static/styles.css`: `.app-signature`, `.app-signature__version`,
  `.app-signature__link`, `.app-signature__icon` — мелкий приглушённый текст
  (`--text-xs`, `--muted-foreground`), значок 14px, hover подсвечивает ссылку.
  Проверка: `::test_signature_has_css_rules`.
- [x] 3.2 `.sidebar__footer .app-signature` — отступ сверху, чтобы подпись не
  читалась как часть профиля.
- [x] 3.3 `.auth__stack`: колонка 400px, `max-width` снят с `.auth__card`
  (карточка тянется на ширину колонки). Без правила разметка входа потеряла бы
  ширину формы.
- [x] 3.4 `.cabinet__signature`: отступ под контентом страниц входа кабинетов.
- [x] 3.5 В `@media (min-width: 1024px)` для `html.sidebar-collapsed` —
  `.app-signature` столбиком: строка «версия + значок» шире полосы 72px.

## 4. Тесты

- [x] 4.1 `tests/test_footer_signature.py`: источник данных (версия = манифест,
  адрес = константа), отсутствие литерала версии в шаблонах, подпись в подвале
  репетитора и кабинетов, внешняя ссылка с `noopener`/`noreferrer` и значком,
  поверхности до входа и 404, единый партиал (≥ 6 включений), CSS-правила.
  Проверка: `uv run pytest tests/test_footer_signature.py -q` — 13 зелёных.

## 5. Регресс

- [x] 5.1 Полный прогон `uv run pytest -n auto` — 2007 тестов зелёные.
- [x] 5.2 Линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py`
  — без ошибок.
- [x] 5.3 Набор иконок не тронут: значок GitHub — не Lucide, `app/static/icons.js`
  не изменился (`tests/test_icons_bundle.py` зелёный).

## Workflow follow-up

- Строку «Добавлено: подпись в подвале — версия и ссылка на GitHub» внести в
  `CHANGELOG.md` при следующем релизе (не отдельным коммитом).
- Архив change'а — после ревью (`openspec archive add-footer-signature`).
