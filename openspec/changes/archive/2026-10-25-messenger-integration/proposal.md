# Proposal

## Why

Уведомления в CRM настраиваются заранее (change `tutor-profile-settings`), но каналов доставки нет: настройки включены, а отправлять их некуда. Репетитору нужен способ получать и рассылать сообщения через мессенджеры (Telegram, MAX, VK), начиная с Telegram — самой простой интеграции (Bot API без OAuth).

## What Changes

- **Общий KV-хранитель параметров репетитора**: новая таблица `tutor_params` («id репетитора + название параметра + значение») — одна строка на пару (репетитор, ключ). Место для произвольных настроек, не только мессенджеров.
- **Доменный модуль `app/messenger`**: отправка сообщений по паттерну «декоратор» —
  - реестр отправителей через Python-декоратор `@register_sender("telegram")`;
  - сквозное поведение — классы-обёртки (GoF Decorator): `LoggingSender` (журнал отправок) и `RetrySender` (повтор при сбое), навешиваемые поверх базового отправителя;
  - функция `send_message(db, tutor_id, messenger, recipient, text)` — диспетчер: указывается мессенджер, получатель и текст, ошибки возвращаются списком;
  - функции подключения: `is_messenger_connected(db, tutor_id, messenger)` и `connected_messengers(db, tutor_id)` — подключён ли репетитор к конкретному мессенджеру / список подключённых.
- **Интеграции с Telegram и MAX**: отправители через Bot API (stdlib `urllib`, без новых зависимостей) — Telegram `sendMessage` и MAX `POST platform-api2.max.ru/messages` (токен в заголовке `Authorization`). VK — закрытый список мессенджеров с подписями, отправитель появится отдельным изменением.
- **Страница `/tutor/settings`** с вкладкой «Мессенджеры» и секциями «Telegram» и «MAX»: поле токена бота, статус подключения («Подключён»/«Не подключён»), сохранение/сброс токена. Пункт сайдбара «Настройки» ведёт на `/tutor/settings` (страница `/tutor/profile` остаётся как есть).

## Capabilities

### Added Capabilities

- `messenger-integration`: отправка сообщений в мессенджеры (реестр отправителей, декораторы-обёртки, Telegram), статусы подключения репетитора и страница настройки мессенджеров.

## Impact

- **Новое**: `app/tutor/models/tutor_param.py`, `app/tutor/services/params.py`, `app/messenger/` (services: `messengers.py`, `errors.py`, `sender.py`, `registry.py`, `logging_sender.py`, `retry_sender.py`, `telegram_sender.py`, `max_sender.py`, `connections.py`, `send.py`), `app/tutor/views/settings.py`, `app/tutor/views/settings_messengers.py`, `app/tutor/services/settings_page.py`, `app/tutor/services/messenger_form.py`, шаблоны `tutor/settings.html` и `tutor/_tab_messengers.html`, миграция Alembic.
- **Изменённое**: `app/models.py` (регистрация модели), `app/tutor/views/__init__.py` (роуты страницы), `app/templates/sidebar.html` (пункт «Настройки»), `app/static/styles.css` (классы секций мессенджеров), `README.md`.
- **Не меняется**: `/tutor/profile` и его вкладки, модель `TutorSettings` (уведомления), существующие миграции.
- **Тесты**: `tests/test_tutor_params.py`, `tests/test_messenger.py`, `tests/test_settings_page.py` — поведение через HTTP, изоляция по репетитору, отправка с подменой HTTP-транспорта.
