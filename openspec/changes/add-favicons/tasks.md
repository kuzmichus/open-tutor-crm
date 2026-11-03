# Tasks

## 1. Исходник и сборка

- [x] 1.1 Скопировать вложение задачи (`deepseek_svg_20261027_f69104.png`, 200×200
  RGBA) в `scripts/vendor/favicon-source.png` — по образцу
  `scripts/vendor/lucide.min.js`: вендорный исходник коммитится, браузеру не
  отдаётся. Проверка: `file scripts/vendor/favicon-source.png` — PNG 200×200 RGBA.
- [x] 1.2 `scripts/build_favicons.py` по образцу `scripts/build_icons.py`:
  docstring «почему так», константы `ROOT`/`SOURCE`/`OUTPUT`, идемпотентная
  генерация, LANCZOS-ресемплинг, проверка размера исходника.
  Проверка: `uv run --with pillow python scripts/build_favicons.py`.
- [x] 1.3 Сгенерировать набор в `app/static/favicons/`: `favicon.ico`
  (16/32/48), `favicon-16x16.png`, `favicon-32x32.png`, `apple-touch-icon.png`
  (180, RGB на белом), `android-chrome-192x192.png`,
  `android-chrome-512x512.png`, `android-chrome-maskable-512x512.png`,
  `favicon.svg`, `safari-pinned-tab.svg`, `site.webmanifest`.
  Проверка: `ls -l app/static/favicons`, размеры PNG — в `tests/test_favicons.py`.

## 2. Подключение

- [x] 2.1 `app/templates/base.html`: сразу после `<title>` и до `styles.css` —
  ссылки `icon` (ico, svg, png 32, png 16), `apple-touch-icon`, `mask-icon`,
  `manifest` и `<meta name="theme-color">`. Комментарий в шаблоне: почему
  локально (AGENTS.md п. 8) и почему набор в `static/favicons`.
- [x] 2.2 Проверить, что `base.html` наследуют все поверхности и ни один шаблон
  не подменяет `<head>` целиком. Проверка: тест 4.4 на четырёх страницах.
- [x] 2.3 `app/common/views/favicon.py`: `GET /favicon.ico` →
  `FileResponse(favicon.ico, media_type="image/vnd.microsoft.icon",
  Cache-Control: no-cache)`; подключить роутер в `app/common/views/__init__.py`.

## 3. Тесты

- [x] 3.1 Все файлы набора существуют и непустые; размеры PNG читаются из IHDR
  вручную, сигнатура PNG проверяется там же.
- [x] 3.2 `favicon.ico`: сигнатура ICONDIR и записи 16/32/48 (0 = 256).
- [x] 3.3 `site.webmanifest`: валидный JSON, `start_url`, `display`,
  каждый `icons[].src` существует на диске и совпадает по размеру.
- [x] 3.4 Head на `/tutor/login`, на 404, на странице кабинета после входа и на
  публичной записи содержит все семь ссылок и `theme-color`; внешних хостов нет.
- [x] 3.5 `GET /static/favicons/{favicon.ico,favicon.svg,apple-touch-icon.png,site.webmanifest}`
  → 200, ожидаемый `content-type` и `Cache-Control: no-cache`.
- [x] 3.6 `GET /favicon.ico` → 200, байты совпадают с файлом на диске.
- [x] 3.7 Прогон `uv run pytest tests/test_favicons.py` — 19 passed;
  смежные `test_css_styles.py`, `test_ui_polish.py`, `test_icons_bundle.py`,
  `test_static_cache.py` — зелёные.

## 4. Спецификация и документация

- [x] 4.1 Change `add-favicons` с delta-spec на новую capability `app-branding`.
  Проверка: `openspec validate add-favicons --strict`.
- [x] 4.2 `CHANGELOG.md`: строка в `[Unreleased] → Добавлено` про favicon,
  PWA-манифест и `theme-color`.
- [x] 4.3 `README.md`: раздел «Иконка сайта» в «Разработке» — команда
  пересборки и пояснение про апскейл из 200 px.
- [x] 4.4 `AGENTS.md` не правится: файл в репозитории — промт окружения задачи
  (коммит `7c7fbde` «AGENTS.md из окружения задачи»), окружение перезаписывает
  его на каждом запуске. Правило про набор favicon живёт в `README.md` и в
  docstring `scripts/build_favicons.py`.
- [x] 4.5 Полный прогон `uv run pytest -n auto` — 2140 passed; линт
  `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py
  scripts/build_favicons.py` — чисто.

## Workflow follow-up

- Визуальная проверка `favicon.svg` и 16/32 px PNG в браузере — единственная
  приёмка векторной версии (см. `design.md`, D7).
- Синхронизировать и архивировать change после ревью.
