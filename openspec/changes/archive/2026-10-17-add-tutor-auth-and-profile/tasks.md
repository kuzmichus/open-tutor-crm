# Tasks

## 1. Модель и миграция

- [x] 1.1 Обновить модель `Tutor` (`app/tutor/models/tutor.py`): id — uuid4 в `String(36)` с генерацией, обязательные name/email/password_hash (nullable только для мигрированных строк), необязательные телефон, «о себе», предмет, опыт, стоимость в час, часовой пояс; сохранить created_at. Проверка: `uv run python -c "from app.tutor.models.tutor import Tutor; print(sorted(c.name for c in Tutor.__table__.columns))"` выводит все новые колонки.
- [x] 1.2 Создать модели `TutorSession` (`app/tutor/models/tutor_session.py`) и `PasswordResetToken` (`app/tutor/models/password_reset_token.py`) по одному классу на файл и добавить их импорты в `app/models.py`. Проверка: `uv run python -c "from app.database import Base; print(sorted(Base.metadata.tables))"` включает `tutor_sessions` и `tutor_password_reset_tokens`.
- [x] 1.3 Написать вручную миграцию после `eb86f21210aa` (autogenerate не видит смену PK): пересоздание `tutors` (id String(36) PK, новые колонки), python-циклом проставить uuid4 существующим строкам, перенести name/email/created_at, unique-индекс на email; осмысленный `downgrade()`. Проверка: на копии dev-базы `uv run alembic upgrade head` завершается без ошибок, прежние записи видны (`SELECT id, name, email`), `uv run alembic downgrade -1` и `uv run alembic upgrade head` проходят.
- [x] 1.4 Обновить существующие тесты под новую схему: фабрика создания репетитора в `tests/conftest.py` (обязательные поля + `password_hash`), поправить `tests/test_pages.py`. Проверка: `uv run pytest` зелёный, страница `/tutors` по-прежнему выводит имя и email.

## 2. Хеширование и сервисы

- [x] 2.1 Создать `PasswordHasher` (`app/tutor/services/password_hasher.py`): PBKDF2-HMAC-SHA256, формат `pbkdf2_sha256$<итерации>$<соль_hex>$<хеш_hex>`, `hash()`/`verify()`; каталог `app/tutor/services/` с `__init__.py`. Проверка: тесты `tests/test_password_hasher.py` — хеш отличается от открытого пароля, `verify()` верен для верного и неверен для неверного пароля, два хеши одного пароля различаются (разные соли), формат распознаётся.
- [x] 2.2 Создать сервис сессий (`app/tutor/services/sessions.py`): создание сессии с `secrets.token_urlsafe(32)` и TTL 7 дней, проверка токена из cookie (жизнеспособность, срок), удаление (logout). Проверка: тесты `tests/test_sessions.py` — создание возвращает валидный токен, неизвестный/подделанный токен отклоняется, истёкшая сессия отклоняется, после удаления токен отклоняется.
- [x] 2.3 Создать сервис ключей восстановления (`app/tutor/services/password_reset.py`): создание ключа (TTL 24 часа), проверка (действует/истёк/использован/несуществующий), погашение (`used_at`). Проверка: тесты `tests/test_password_reset_service.py` — свежий ключ валиден, ключ с `expires_at` в прошлом отклоняется, погашённый ключ отклоняется, неизвестный ключ отклоняется.

## 3. Регистрация, вход, кабинет, выход

- [x] 3.1 Создать регистрацию `app/tutor/views/register.py` (`GET+POST /tutor/register`) и шаблон `app/tutor/templates/tutor/register.html`; валидация (email, непустой пароль, дубликат email — сообщение без создания аккаунта), пароль хешируется, успех — `303` на `/tutor/login`. Проверка: тесты `tests/test_register.py` — успех создаёт репетитора и редиректит, пароль в базе != открытому, дубликат email и невалидные данные не создают аккаунт и возвращают форму с сообщением.
- [x] 3.2 Создать вход `app/tutor/views/login.py` (`GET+POST /tutor/login`) и шаблон `login.html`; верный пароль — сессия, httpOnly-cookie, `303` на `/tutor/`; неверный пароль или неизвестный email — единое сообщение «Неверный email или пароль», без сессии. Проверка: тесты `tests/test_login.py` — успех (cookie установлен, редирект), обе причины отказа дают одинаковое сообщение и не открывают сессию.
- [x] 3.3 Создать кабинет `app/tutor/views/home.py` (`GET /tutor/`) и шаблон `home.html`; без живой сессии — редирект на `/tutor/login`, с сессией — карточка вошедшего со всеми полями. Проверка: тесты `tests/test_home.py` — без cookie редирект, с валидной сессией отображаются данные вошедшего и не отображаются данные другого репетитора, подделанный токен приводит к редиректу.
- [x] 3.4 Создать выход `app/tutor/views/logout.py` (`POST /tutor/logout`): удаляет сессию, `303` на `/tutor/login`; подключить все новые роутеры в `app/tutor/views/__init__.py`. Проверка: тесты `tests/test_logout.py` — после выхода прежняя cookie отклоняется и `/tutor/` редиректит на login.

## 4. Восстановление пароля

- [x] 4.1 Создать `app/tutor/views/remember_password.py` (`GET+POST /tutor/remember-password`) и шаблон `remember_password.html`: существующий email — создаётся ключ и на странице отображается ссылка `/tutor/reset-password?key=...`; неизвестный email — нейтральное сообщение без ссылки и без раскрытия существования аккаунта. Проверка: тесты `tests/test_remember_password.py` — оба сценария (ссылка присутствует / нейтральное подтверждение без ссылки).
- [x] 4.2 Создать `app/tutor/views/reset_password.py` (`GET+POST /tutor/reset-password?key=...`) и шаблон `reset_password.html`: действующий ключ — форма; POST с непустым паролем хеширует новый пароль и погашает ключ, `303` на `/tutor/login`; несуществующий, использованный или истёкший ключ и пустой пароль — сообщение об ошибке без смены пароля. Проверка: тесты `tests/test_reset_password.py` — успешный сброс (новый пароль входит, старый нет, ключ нельзя использовать повторно), несуществующий ключ, пустой пароль и повторное использование отклонены.
- [x] 4.3 Добавить сценарий истёкшего ключа: в тестах ключ создаётся с `expires_at` в прошлом. Проверка: тест в `tests/test_reset_password.py` — GET показывает сообщение о недействительной ссылке без формы, POST не меняет пароль.

## 5. Интеграционная проверка

- [x] 5.1 Полный прогон тестов и схемы. Проверка: `uv run pytest` — все тесты зелёные; `uv run alembic upgrade head` без ошибок; `uv run alembic revision --autogenerate -m "check"` не показывает незафиксированных изменений схемы (сгенерированный файл удалить).
- [x] 5.2 Ручная сквозная проверка на копии dev-базы: `uv run uvicorn main:app --port 8000` — `/tutors` показывает перенесённые записи; цепочка регистрация → `/tutor/` → logout → login → `/tutor/` → remember-password → переход по ссылке → сброс → вход новым паролем работает в браузере.

## 6. Правка по замечанию: состав формы регистрации

- [x] 6.1 В форме регистрации оставить только имя, email, пароль и подтверждение пароля: обновить `app/tutor/templates/tutor/register.html` и `app/tutor/views/register.py` (валидация «Пароли не совпадают»); необязательные поля карточки по-прежнему принимать в POST (импорт/API). Проверка: `uv run pytest tests/test_register.py` — тест `test_form_asks_only_name_email_password_and_confirm` подтверждает состав полей.
- [x] 6.2 Согласовать артефакты: обновить дельту `specs/tutor-auth/spec.md` (состав формы + сценарий несовпадения паролей), `design.md` (D6) и `proposal.md`. Проверка: `openspec validate "add-tutor-auth-and-profile"` проходит, `uv run pytest` — все тесты зелёные.

## 7. Правка: отказ от лишних полей POST и удаление `/tutors`

- [x] 7.1 `POST /tutor/register` принимает только имя, email, пароль и подтверждение: убрать необязательные поля и разбор `hourly_rate` из `app/tutor/views/register.py`. Проверка: `uv run pytest tests/test_register.py` — тест `test_extra_post_fields_are_ignored` подтверждает, что лишние поля не сохраняются.
- [x] 7.2 Удалить ручку `/tutors` полностью: `app/tutor/views/index.py`, `app/tutor/templates/tutor/index.html`, подключение в `views/__init__.py`, ссылки в `login.html`/`home.html`, тесты страницы в `tests/test_pages.py` (добавлен тест 404). Проверка: `uv run pytest` — `test_tutors_list_page_removed` даёт 404.
- [x] 7.3 Согласовать артефакты: `specs/tutor-records/spec.md` (убрано требование о странице-списке, обновлён Purpose), `specs/tutor-auth/spec.md` (сценарий «Лишние поля игнорируются»), `proposal.md`, `design.md`, `README.md`. Проверка: `openspec validate --strict` проходит, `uv run pytest` — зелёный.
