# Proposal

## Why

Редактор лендинга (`add-landing-editor`) открывает черновик в GrapesJS, но
Asset Manager не умеет загружать картинки: upload URL не настроен, а в
`landing/assets/` нечего показать. Репетитор не может добавить изображение
на страницу без правки файлов на диске.

## What Changes

- `POST /tutor/landing/assets` — multipart-загрузка из Asset Manager:
  белый список `jpg, jpeg, png, gif, webp, svg`, лимит
  `FILES_MAX_SIZE_MB`, для растров проверка магических байтов. Имя файла
  генерирует сервер (`uuid4` + расширение), запись — `save_asset()`.
  Ответ — JSON `{"data": [{src: "/landing-assets/<uuid>.<ext>", type:
  "image"}]}`, который `autoAdd` GrapesJS кладёт в коллекцию ассетов.
- `DELETE /tutor/landing/assets/{filename}` — удаление файла с диска; имя
  проверяется тем же строгим шаблоном, что и на публичной отдаче.
- В шаблон редактора вшивается JSON текущих ассетов (`list_assets()`), а
  `grapesjs.init` получает `assetManager: { upload, uploadName: 'files',
  uploadText, assets }`. Ссылки вставляемых картинок абсолютные
  (`/landing-assets/…`): `/` и предпросмотр показывают одну и ту же
  страницу.
- В JS редактора `asset:remove` отправляет `DELETE` и удаляет файл с
  диска; `asset:remove:before` показывает текст подтверждения, потому что
  удалённый файл ломает ссылку на странице. `asset:upload:*` показывают
  «Загрузка…» и понятную причину отказа.
- Оба роута требуют `require_tutor_id` и доступны только в сингл-режиме
  (404 в мульти-режиме).
- Тесты `tests/test_landing_assets.py` и unit-тесты
  `is_valid_asset_content` в `tests/test_landing_storage.py`.

**Вне области:**

- Хранение ассетов в БД или `FILES_*`: только диск, `LANDING_ROOT`.
- Редактирование/переименование ассетов, отдельный лимит размера для
  лендинга, чистка ассетов без ссылок.

## Capabilities

### New Capabilities

— (нет; расширяется существующая `landing-page`)

### Modified Capabilities

- `landing-page`: загрузка картинок из редактора, удаление картинки,
  инициализация Asset Manager и проверка содержимого растров.

## Impact

- `app/landing/services/storage.py` — сигнатуры растров и
  `is_valid_asset_content`.
- `app/landing/views/assets.py` — управляющие роуты загрузки и удаления.
- `app/landing/views/editor.py`, `app/landing/templates/landing/editor.html` —
  список ассетов и настройка Asset Manager.
- `tests/test_landing_assets.py`, `tests/test_landing_storage.py`.
- `README.md`, `CHANGELOG.md`, спека `landing-page`.
- Схема БД, миграции, `LANDING_ROOT` и `FILES_*` не меняются.
