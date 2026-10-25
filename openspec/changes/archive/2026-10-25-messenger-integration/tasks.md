# Tasks

## 1. Хранение параметров

- [x] 1.1 Модель `TutorParam` (`app/tutor/models/tutor_param.py`): составной PK `(tutor_id, key)`, FK на `tutors` с CASCADE, `value` NOT NULL; регистрация в `app/models.py`.
- [x] 1.2 Сервис `app/tutor/services/params.py`: `get_param`, `set_param` (upsert), `delete_param`, `all_params`.
- [x] 1.3 Миграция Alembic `tutor_params` (autogenerate, поверх `675dadfd810e`).

## 2. Модуль `app/messenger`

- [x] 2.1 `services/messengers.py`: `MESSENGERS = ("telegram", "max", "vk")`, подписи, `token_key()`.
- [x] 2.2 `services/errors.py`: `SendError`; `services/sender.py`: протокол `Sender`.
- [x] 2.3 `services/registry.py`: декоратор `@register_sender` + `get_sender_class`.
- [x] 2.4 Обёртки-декораторы: `services/logging_sender.py`, `services/retry_sender.py`.
- [x] 2.5 `services/telegram_sender.py`: TelegramSender (Bot API, urllib, таймаут 10 c).
- [x] 2.6 `services/connections.py`: `is_messenger_connected`, `connected_messengers`.
- [x] 2.7 `services/send.py`: `send_message` — валидация, сборка цепочки декораторов, ошибки списком.

## 3. Страница `/tutor/settings`

- [x] 3.1 Сервисы: `settings_page.py` (вкладки, статусы подключения, форма), `messenger_form.py` (разбор и валидация токена).
- [x] 3.2 Вьюхи: `settings.py` (GET), `settings_messengers.py` (POST); сборка в `app/tutor/views/__init__.py`.
- [x] 3.3 Шаблоны `tutor/settings.html`, `tutor/_tab_messengers.html`; пункт сайдбара «Настройки» → `/tutor/settings`.
- [x] 3.4 CSS: классы секции мессенджера (`.messenger*`) в `app/static/styles.css`.

## 4. Тесты и документация

- [x] 4.1 `tests/test_tutor_params.py`: upsert/чтение/удаление, изоляция по репетитору.
- [x] 4.2 `tests/test_messenger.py`: реестр, подключения, отправка с подменой urllib (успех/ошибка API/сеть), ретрай, неизветсный мессенджер, «не подключён».
- [x] 4.3 `tests/test_settings_page.py`: доступ, вкладка и секция Telegram, сохранение/сброс токена, ошибка формата, изоляция.
- [x] 4.4 README: краткое описание интеграции и страницы.
- [x] 4.5 `uv run pytest` зелёный.

## 5. Интеграция с MAX

- [x] 5.1 `services/max_sender.py`: MaxSender — `POST platform-api2.max.ru/messages?chat_id=…`, токен в заголовке `Authorization` (без префикса), ошибки `{code, message}` → `SendError`.
- [x] 5.2 `messengers.py`: MAX в `SUPPORTED`, подсказки и плейсхолдеры секций.
- [x] 5.3 Форма и вьюха обобщены на несколько токенов (`messenger_form.py` — форматы по мессенджеру, вьюха сохраняет/удаляет каждый).
- [x] 5.4 Тесты: реестр, отправка MAX (успех/ошибка API/сеть/неожиданный ответ), порядок `connected_messengers`, поля и статусы на странице, независимое сохранение токенов.
