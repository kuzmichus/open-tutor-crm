# Proposal

## Why

Опубликованный лендинг отдаётся с `/` как чистый статический файл, поэтому
вошедший ученик, родитель или репетитор видел те же ссылки «Вход для ученика»,
«Вход для родителя» и «вход», что и аноним. Задача закрывает этот разрыв
клиентски: страница остаётся статической, а кнопки сами меняются на «В
кабинет» или «кабинет» по факту живой сессии.

## What Changes

- Новый публичный `GET /auth/status` в общем модуле
  (`app/common/views/auth_status.py`): JSON `{"student", "parent", "tutor"}` по
  трём существующим сессиям и `Cache-Control: no-store`.
- Новый ванильный скрипт `app/static/landing-auth.js`: на `DOMContentLoaded`
  запрашивает статус и для `[data-auth]` подменяет текст и `href`; без
  элемента, сессии или при сбое — молчаливый no-op.
- Подключение роутера в `app/common/views/__init__.py`.
- Тесты `tests/test_landing_auth_status.py`: JSON, `no-store`, три сессии,
  комбинации, отсутствующие/лишние/протухшие cookie и отдача статики.
- Документация: требование в спеке `landing-page`, README и CHANGELOG.

**Вне области:**

- Тег `<script src="/static/landing-auth.js" defer>` в шаблоне и его
  восстановление после правок редактора — задачи 2 и 4; здесь только
  эндпоинт и скрипт.
- Серверный рендер страницы: `/` по-прежнему отдаёт файл как есть.

## Capabilities

### New Capabilities

— (нет; расширяется существующая `landing-page`)

### Modified Capabilities

- `landing-page`: статус входа по трём сессиям и клиентская подмена кнопок
  входа на опубликованной странице.

## Impact

- `app/common/views/auth_status.py`, `app/common/views/__init__.py`.
- `app/static/landing-auth.js`.
- `tests/test_landing_auth_status.py`.
- `openspec/specs/landing-page/spec.md`, `README.md`, `CHANGELOG.md`.
- Схема БД, миграции и шаблон лендинга не меняются.
