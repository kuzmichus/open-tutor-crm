# Tasks

## 1. Разметка переключателя

- [x] 1.1 В `app/templates/sidebar.html` добавить в `.sidebar__footer` блок `.sidebar__theme` с двумя кнопками `.theme-switch__btn`: «Светлая» (`data-theme-toggle="light"`, иконка `sun`, `aria-pressed="true"`) и «Тёмная» (`data-theme-toggle="dark"`, иконка `moon`, `aria-pressed="false"`), обе — `type="button"`, с `title` и текстом внутри `span`; блок ставится **выше** `.user-row-wrap`; проверка: тест в `tests/test_sidebar.py` — оба `data-theme-toggle`, обе иконки, обе подписи, `theme-switch` идёт после `sidebar__footer` и до `user-row-wrap`
- [x] 1.2 В `app/templates/base.html` расширить бутстрап-скрипт в `<head>`: если в `localStorage` `opentutorcrm:theme` равен `"dark"`, добавить класс `dark` на `<html>` до отрисовки (в том же `try/catch`, что и `sidebar-collapsed`); проверка: тест — в `<head>` страницы входа есть `opentutorcrm:theme` и `classList.add("dark")`

## 2. Поведение переключения

- [x] 2.1 В `app/static/app.js` переписать блок темы: `applyTheme(theme)` ставит/снимает класс `dark` и синхронизирует `aria-pressed` у всех `[data-theme-toggle]`; обработчик читает значение из `data-theme-toggle` (идемпотентно), вызывает `applyTheme` и пишет выбор в `localStorage`; при инициализации применяется сохранённая тема, иначе `light`; проверка: тест — `applyTheme`, `data-theme-toggle`, `opentutorcrm:theme` и `classList.toggle("dark"` присутствуют в `app.js`

## 3. Оформление

- [x] 3.1 В `app/static/styles.css` описать `.sidebar__theme`, `.theme-switch`, `.theme-switch__btn` на токенах сайдбара (иконка 16px, `min-height` 32px, `font-size: var(--text-xs)`), и правило активного сегмента `html:not(.dark) .theme-switch__btn[data-theme-toggle="light"], html.dark .theme-switch__btn[data-theme-toggle="dark"]`; плоские BEM-селекторы, без `&__`; проверка: тест — `.theme-switch__btn` и оба правила активного сегмента есть в `styles.css`
- [x] 3.2 В медиа-блоке `html.sidebar-collapsed .sidebar` скрыть подписи сегментов и убрать их боковые отступы (`.theme-switch__btn span { display: none }`, `padding: 0`), чтобы контрол помещался в полосу 72px; проверка: `uv run pytest tests/test_sidebar.py -q` зелёные

## 4. Проверка в браузере и документация

- [x] 4.1 Браузерный сценарий (Chromium headless): светлая тема → клик «Тёмная» → страница тёмная, выделен «Тёмная»; перезагрузка страницы → тёмная тема без вспышки светлого, выделен «Тёмная»; клик «Светлая» → светлая; свёрнутый сайдбар → оба сегмента видны как иконки, переключение работает; консоль без ошибок
  <!-- Результат (2026-10-22, Chromium headless, http://127.0.0.1:8011, 30/30 шагов PASS):
       футер сайдбара показывает сегменты «Светлая»/«Тёмная» выше строки пользователя,
       в светлой теме выделена «Светлая»; клик «Тёмная» перекрашивает страницу без
       перезагрузки и выделяет «Тёмная»; после перехода на /tutor/ тема сохраняется
       (класс .dark ставится бутстрапом в <head>, вспышки светлого фона нет);
       клик «Светлая» возвращает светлое оформление; в свёрнутом сайдбаре (72px)
       оба сегмента остаются видимыми как иконки (sun/moon) и переключают тему.
       Артефакты: test-result/2026-10-21T20-23-43-808Z/ (summary.md, screenshots,
       video.mp4). -->

- [x] 4.2 Дописать в `README.md` (раздел «Возможности») пункт про переключение светлой и тёмной темы в сайдбаре
- [x] 4.3 Полный прогон `uv run pytest` — все тесты зелёные; `openspec validate add-theme-switch --strict` — без ошибок
