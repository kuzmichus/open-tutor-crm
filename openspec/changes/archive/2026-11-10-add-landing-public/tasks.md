# Tasks

## 1. Конфигурация и модуль

- [x] 1.1 `app/config.py`: поле `landing_root: str = "./landing"` с
  комментарием по образцу `files_local_root`.
- [x] 1.2 Новый пакет `app/landing/` (`__init__.py`, `services/`, `views/`) по
  конвенции проекта; моделей нет.
- [x] 1.3 `Dockerfile`: `ENV LANDING_ROOT=/data/landing` рядом с
  `DATABASE_URL`, каталог `/data/landing` создаётся и отдаётся пользователю
  `app`.
- [x] 1.4 `.gitignore` и `.dockerignore`: `/landing/` и `landing/` — данные
  dev-сервера, не код.

## 2. Дисковое хранилище

- [x] 2.1 `app/landing/services/storage.py`: `LandingStorage` с путями
  `draft_path`, `index_path`, `prev_path`, `assets_dir`, `asset_path(name)`.
- [x] 2.2 Чтения: `has_draft()`, `has_published()`, `read_draft_html()`
  (`None` при отсутствии), `list_assets()` — без исключений и без создания
  каталогов.
- [x] 2.3 Запись: `save_draft(html)` через временный файл и `os.replace`;
  `_write_atomic` создаёт каталоги лениво.
- [x] 2.4 `publish()`: `index.html` → `index.prev.html` (перезапись), затем
  `draft.html` → `index.html`; без черновика — `False`. `unpublish()` удаляет
  только `index.html`.
- [x] 2.5 Ассеты: `save_asset(filename, content)` — `uuid4` + нормализованное
  расширение из allowlist, возвращает имя; `remove_asset(name)` терпит
  отсутствие; `asset_path` отвергает разделители и `..`.
- [x] 2.6 `ASSET_NAME_PATTERN` / `is_asset_name(name)` — строгий шаблон
  сгенерированного имени (uuid4 + картинка).
- [x] 2.7 `get_storage()` — хранилище по текущему `settings.landing_root`.

## 3. Публичная выдача

- [x] 3.1 `app/landing/services/access.py`: `landing_enabled()` (сингл-режим),
  `published_landing()` — путь к `index.html` либо `None`.
- [x] 3.2 `app/common/views/index.py`: при опубликованной странице —
  `FileResponse(index.html, media_type="text/html", Cache-Control: no-cache)`;
  иначе прежний 303 на `/tutor/`.
- [x] 3.3 `app/landing/views/assets.py`: `GET /landing-assets/{filename}`,
  проверка имени по шаблону (иначе 404), тип по расширению, кэш
  `public, max-age=31536000, immutable`.
- [x] 3.4 `app/landing/views/__init__.py` и `main.py`: роутер ассетов подключён
  к приложению.

## 4. Тесты

- [x] 4.1 `tests/test_landing_storage.py`: пустой корень, ленивые каталоги,
  пути, черновик, публикация с бэкапом и перезаписью, отмена публикации,
  ассеты (uuid-имена, allowlist, список, удаление), защита `asset_path`,
  `is_asset_name`, дефолт и env `LANDING_ROOT`.
- [x] 4.2 `tests/test_landing_public.py`: 303 без публикации и в мульти-режиме,
  200 с содержимым и `no-cache` после публикации, свежая версия, черновик
  наружу не отдаётся, `<script>` сохраняется, ассеты (типы, кэш, публичность,
  404 на произвольное/отсутствующее имя), 303 после `unpublish()`.
- [x] 4.3 Прогон `uv run pytest -n auto` — 2469 тестов зелёные; линт
  `ruff check --select E9,F63,F7,F82 app/ tests/ main.py cron.py`.

## 5. Спецификация и документация

- [x] 5.1 Delta-спека `landing-page`: хранение, публикация, отдача `/`,
  ассеты, allowlist картинок.
- [x] 5.2 `openspec/changes/add-landing-public/`: `proposal.md`, `design.md`
  (решения D1–D7), `tasks.md`, `.openspec.yaml`.
- [x] 5.3 `README.md`: строка `LANDING_ROOT` в таблице «Конфигурация» и раздел
  «Лендинг».
- [x] 5.4 `CHANGELOG.md`: пункт в `[Unreleased] → Добавлено`.
