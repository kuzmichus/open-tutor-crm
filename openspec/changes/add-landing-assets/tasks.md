# Tasks

## 1. Сервис хранилища

- [x] 1.1 `is_valid_asset_content(filename, content)`: сигнатуры PNG, JPEG,
  GIF, WEBP; SVG по непустому телу; пустое тело — невалидно.
- [x] 1.2 `save_asset` не меняется: проверка содержимого — обязанность
  вьюхи загрузки.

## 2. Роуты ассетов

- [x] 2.1 `POST /tutor/landing/assets`: multipart, поля `files` и
  `files[]`, белый список расширений, лимит `FILES_MAX_SIZE_MB`, чтение
  чанками с обрывом, проверка сигнатур, атомарная валидация набора.
- [x] 2.2 Ответ `{"data": [{src, type}]}` с `Cache-Control: no-store`;
  сообщения об отказе — `{"error": "…"}` на русском.
- [x] 2.3 `DELETE /tutor/landing/assets/{filename}`: проверка
  `is_asset_name`, идемпотентное удаление, 204.
- [x] 2.4 Оба роута: `require_tutor_id` и 404 в мульти-режиме.

## 3. Asset Manager в редакторе

- [x] 3.1 `views/editor.py`: список ассетов `{src, type}` из
  `list_assets()` с фильтром `is_asset_name`.
- [x] 3.2 `editor.html`: JSON `landing-assets`, конфиг
  `assetManager: { upload, uploadName: 'files', uploadText, assets }`,
  переопределение `assetManager.uploadTitle` в русской локали.
- [x] 3.3 `asset:remove` → `fetch DELETE` по имени из `/landing-assets/…`;
  `asset:remove:before` → подтверждение с предупреждением о битой ссылке.
- [x] 3.4 `asset:upload:start/end/error`: «Загрузка…», очистка статуса и
  разбор `{"error"}` / `{"detail"}` ответа.

## 4. Тесты

- [x] 4.1 `tests/test_landing_assets.py`: успешная загрузка всех форматов,
  поля `files` и `files[]`, несколько файлов, неуникальные имена.
- [x] 4.2 Отказы: расширение, сигнатура, пустой файл, лимит, атомарность
  набора.
- [x] 4.3 Доступ: сессия, мульти-режим, публичная отдача.
- [x] 4.4 Удаление: 204, 404 на ссылку, идемпотентность, невалидные имена.
- [x] 4.5 Страница редактора: JSON ассетов и настройка Asset Manager.
- [x] 4.6 Unit-тесты `is_valid_asset_content` в
  `tests/test_landing_storage.py`.

## 5. Документация

- [x] 5.1 `README.md`: Asset Manager в разделе «Лендинг».
- [x] 5.2 `CHANGELOG.md`: запись в `[Unreleased] → Добавлено`.
- [x] 5.3 Спека `landing-page`: требования загрузки, удаления и
  инициализации Asset Manager; delta в
  `openspec/changes/add-landing-assets/`.

## 6. Проверка

- [x] 6.1 `uv run pytest tests/test_landing_*.py -q`.
- [x] 6.2 Полный прогон `uv run pytest -n auto` (2586 passed) и
  `ruff check` (E9,F63,F7,F82 и полный набор для модуля лендинга).
- [ ] 6.3 Проверка в браузере: сценарий прогнан HTTP-запросами на
  поднятом стенде (загрузка, вставка в черновик, публикация, удаление,
  404 по ссылке, отказы) — визуальная проверка модального окна Asset
  Manager остаётся за тестировщиком.
