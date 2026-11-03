# Tasks

## 1. Исходник и сборка

- [x] 1.1 Заменить `scripts/vendor/favicon-source.png` новым вложением задачи
  (`deepseek_svg_20261017_fdaaca.png`, 200×200 RGBA). Проверка: PNG 200×200 RGBA.
- [x] 1.2 Переписать `scripts/build_favicons.py` под новый знак: константы
  геометрии (фон-сквиркл, облако с хвостиком, солнце), цвета градиента
  `#F97316 → #EC4899`, `theme-color` `#F66838`; `_on_gradient` (apple-touch на
  градиенте), `_mark_mask`/`_maskable` (safe zone 80 %), векторные пути
  `_favicon_svg`/`_pinned_tab_svg`. Docstring «почему так» сохранён.
  Проверка: `uv run --with pillow python scripts/build_favicons.py` — «файлов: 10».
- [x] 1.3 Пересобрать набор в `app/static/favicons/` (10 файлов). Проверка:
  размеры PNG — в `tests/test_favicons.py`; ICO — 16/32/48.

## 2. Подключение

- [x] 2.1 `app/templates/base.html`: `theme-color` и `mask-icon color` →
  `#F66838`; комментарий про `apple-touch-icon` обновлён (сводится на
  продолжение градиента, а не на белый).

## 3. Тесты и проверка

- [x] 3.1 `tests/test_favicons.py`: `theme-color` в `<head>` сверяется с
  `theme_color` из `site.webmanifest`, а не с захардкоженным значением.
- [x] 3.2 Визуальная сверка `favicon.svg` с растром в headless Chrome:
  расхождение 0.09 % (30 из 33741 пикселей, крайние углы, альфа ≤ 63), лишних
  пикселей нет.
- [x] 3.3 `uv run pytest tests/test_favicons.py` — 19 passed.

## 4. Спецификация и документация

- [x] 4.1 Change `replace-favicon` (`proposal.md`, `design.md`, `tasks.md`) без
  delta-spec: требования `app-branding` не меняются.
- [x] 4.2 `CHANGELOG.md`: строка в `[Unreleased] → Изменено` про замену знака,
  пересборку набора и новый `theme-color`.

## Workflow follow-up

- Визуальная проверка `favicon.svg` и 16/32 px PNG в браузере — приёмка
  векторной версии (см. `design.md`, D4).
- Синхронизировать изменение `app-branding` (если/когда спека появится из
  `add-favicons`) и архивировать change после ревью.