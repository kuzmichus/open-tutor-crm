# Tasks

## 1. OpenSpec

- [x] 1.1 Change `add-file-uploads`: `proposal.md`, `design.md`, `tasks.md`,
  delta-спека `specs/file-storage/spec.md` (новая capability) и правка
  `specs/homework-management/spec.md` (требование «Поля ДЗ без файлов и
  автоматики» заменено загрузкой файлов).

## 2. Конфигурация

- [x] 2.1 `app/config.py`: поля `files_backend` (`local`/`s3`),
  `files_local_root`, `files_max_size_mb`, `files_allowed_extensions`,
  `files_presign_ttl_seconds`, `s3_bucket`, `s3_region`, `s3_endpoint_url`,
  `s3_access_key_id`, `s3_secret_access_key`, `s3_prefix`.
- [x] 2.2 Там же `@model_validator(mode="after")`: `s3` требует бакет и ключи,
  `local` — только корень. Проверка: `tests/test_file_storage.py`.

## 3. Абстракция хранения

- [x] 3.1 `app/files/services/storage.py`: ABC `Storage` (`save`, `open`,
  `delete`, `exists`, `download_url`).
- [x] 3.2 `app/files/services/storage_local.py`: `LocalStorage` — защита от
  выхода за корень, запись через временный файл и `os.replace`, создание корня.
- [x] 3.3 `app/files/services/storage_s3.py`: `S3Storage` на `boto3` — префикс
  ключа, presigned URL с `ExpiresIn`, подставляемая фабрика клиента.
- [x] 3.4 `app/files/services/storage_factory.py`: `get_storage()` под
  `lru_cache`, выбор бэкенда по env.

## 4. Модели и миграция

- [x] 4.1 `app/files/models/stored_file.py`: `StoredFile` (таблица `files`) с
  CHECK по списку бэкендов и UNIQUE на ключ.
- [x] 4.2 `app/files/models/homework_file.py`: `HomeworkFile` (таблица
  `homework_files`) — связь файла с ДЗ и порядок.
- [x] 4.3 `app/models.py`: импорты-регистраторы новых моделей.
- [x] 4.4 Миграция Alembic (`down_revision='a7d3e1f42b90'` — текущая голова
  main; `alembic upgrade head` и `alembic check` зелёные).

## 5. Сервисы файлов

- [x] 5.1 `app/files/services/upload.py`: `validate_upload`, `build_key`,
  `save_upload` — чтение чанками с обрывом по лимиту.
- [x] 5.2 `app/files/services/removal.py`: `delete_file`,
  `delete_homework_files` — сначала объект, потом строка.
- [x] 5.3 `app/files/services/removal.py`: `files_of_homework` и
  `files_of_homeworks` (пакетная выборка для списков, без N+1).
- [x] 5.4 `app/files/services/access.py`: `resolve_downloadable_file` — три
  актора, чужое = 404.
- [x] 5.5 `app/files/services/presentation.py`: `file_size_label` и
  регистрация хелпера в `app/templating.py`.

## 6. Вьюхи

- [x] 6.1 `app/files/views/download.py`: `GET /files/{file_id}` — 302 на
  presigned URL для S3, `FileResponse` с защитными заголовками для локального.
- [x] 6.2 `app/files/views/__init__.py`, подключение роутера в `main.py`.
- [x] 6.3 `app/homework/views/save.py`: приём файлов формы панели, откат ДЗ при
  ошибке файла.
- [x] 6.4 `app/homework/views/delete_file.py`: удаление файла ДЗ и
  перерендер панели.

## 7. Панель ДЗ и кабинеты

- [x] 7.1 `app/homework/services/homework_context.py`: `hw_files` в контексте.
- [x] 7.2 `app/homework/templates/homework/_panel.html`: поле выбора файлов
  (`multiple`, `hx-encoding`), партиал `_files.html` со списком и удалением.
- [x] 7.3 `app/static/styles.css`: правила для новых BEM-классов.
- [x] 7.4 Кабинеты: файлы ДЗ в карточке ученика и на вкладке родителя.

## 8. Уборка при каскадных удалениях

- [x] 8.1 `app/lesson/services/lesson_remover.py`: удаление объектов ДЗ уроков
  перед удалением урока и серии.

## 9. Тесты

- [x] 9.1 `tests/test_file_storage.py`: локальный и S3-бэкенды на заглушке
  клиента, защита от `..`, выбор бэкенда фабрикой, валидатор конфигурации.
- [x] 9.2 `tests/test_file_upload.py`: загрузка, лимит размера, запрещённое
  расширение, скачивание владельцем/учеником/родителем, 404 посторонним,
  удаление, S3-редирект.
- [x] 9.3 `tests/test_homework.py`: тест панели проверяет поле файлов вместо
  кнопки-заглушки.
- [x] 9.4 `tests/test_cabinet_homework.py`: файлы видны ученику и родителю.

## 10. Зависимости, окружение, документация

- [x] 10.1 `pyproject.toml` + `uv lock`: `boto3`.
- [x] 10.2 `Dockerfile` (`FILES_LOCAL_ROOT=/data/files`), `.dockerignore`,
  `.gitignore`.
- [x] 10.3 `README.md`: строки конфигурации и раздел про хранение файлов;
  `CHANGELOG.md`.

## 11. Проверки

- [x] 11.1 `uv run pytest -n auto`, `alembic upgrade head && alembic check`,
  `uv lock --check`, `ruff check --select E9,F63,F7,F82`,
  `python scripts/smoke_demo.py`.
- [x] 11.2 `openspec validate add-file-uploads --strict`.

## Workflow follow-up

- Синхронизировать и архивировать change после ревью.
