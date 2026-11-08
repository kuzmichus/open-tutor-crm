# Tasks

## 1. Эндпоинт статуса

- [x] 1.1 `app/common/views/auth_status.py`: публичный `GET /auth/status`,
  JSON `{"student", "parent", "tutor"}` по трём хелперам сессий.
- [x] 1.2 Заголовок `Cache-Control: no-store`.
- [x] 1.3 `app/common/views/__init__.py`: подключить роутер статуса.

## 2. Клиентский скрипт

- [x] 2.1 `app/static/landing-auth.js`: ванильный IIFE без зависимостей.
- [x] 2.2 На `DOMContentLoaded` — `fetch("/auth/status")`; таблица ролей
  `student`/`parent`/`tutor` с текстами и ссылками.
- [x] 2.3 Подмена только у `[data-auth]`, молчаливый no-op при сбое,
  отсутствии элемента или `false`.

## 3. Тесты

- [x] 3.1 `tests/test_landing_auth_status.py`: аноним, JSON и `no-store`,
  отсутствие редиректа.
- [x] 3.2 Параметризация по трём живым сессиям и проверка комбинаций.
- [x] 3.3 Поддельная, лишняя и протухшая cookie дают `false`.
- [x] 3.4 Отдача `/static/landing-auth.js` с нужными строками.

## 4. Документация

- [x] 4.1 `openspec/specs/landing-page/spec.md`: требование статуса и
  подмены кнопок.
- [x] 4.2 `openspec/changes/add-landing-auth-status/`: proposal, design,
  tasks, delta-спека, `.openspec.yaml`.
- [x] 4.3 `README.md` и `CHANGELOG.md`: описание клиентской подмены кнопок.
