# Tasks

## 1. Конфигурация почты

- [x] 1.1 `app/config.py`: поля `smtp_host`, `smtp_port` (587),
  `smtp_username`, `smtp_password`, `smtp_from`, `smtp_starttls` (True),
  `smtp_use_ssl` (False), `smtp_timeout` (15), `app_base_url` (пусто).
- [x] 1.2 `app/config.py`: валидатор `_check_smtp_settings` — при заданном
  `SMTP_HOST` требуются отправитель (`SMTP_FROM` или `SMTP_USERNAME`),
  положительные порт и таймаут, взаимоисключающие `SMTP_USE_SSL` и
  `SMTP_STARTTLS`.
- [x] 1.3 `app/config.py`: свойства `email_enabled` (включён ли `SMTP_HOST`)
  и `mail_from` (`SMTP_FROM`, иначе `SMTP_USERNAME`).

## 2. Транспорт SMTP

- [x] 2.1 `app/mail/__init__.py`, `app/mail/services/__init__.py`: пакет
  модуля и docstring.
- [x] 2.2 `app/mail/services/sender.py`: `email_enabled()`.
- [x] 2.3 `app/mail/services/sender.py`: `build_message(...)` —
  `multipart/alternative` в UTF-8, `From` с именем приложения,
  `Message-ID` с доменом отправителя, текстовая часть с fallback.
- [x] 2.4 `app/mail/services/sender.py`: `send_email(...)` — проверки
  получателя/темы/включённости, ошибки списком строк, логирование сбоев.
- [x] 2.5 `app/mail/services/sender.py`: `_deliver` — `SMTP_SSL` при
  `SMTP_USE_SSL`, иначе STARTTLS по `SMTP_STARTTLS`; логин только при
  заданном `SMTP_USERNAME`.

## 3. Письмо восстановления пароля

- [x] 3.1 `app/tutor/templates/email/password_reset.html`: HTML-часть
  письма (inline-стили, табличная вёрстка, кнопка и голая ссылка).
- [x] 3.2 `app/tutor/templates/email/password_reset.txt`: текстовая часть.
- [x] 3.3 `app/tutor/services/password_reset_email.py`:
  `send_password_reset_email(*, to_email, tutor_name, reset_url)` — рендер
  шаблонов, тема, срок из `TTL`, вызов `send_email`.

## 4. Вьюха восстановления

- [x] 4.1 `app/tutor/views/remember_password.py`: `_reset_url` — абсолютная
  ссылка от `APP_BASE_URL`, иначе от `request.base_url`.
- [x] 4.2 `app/tutor/views/remember_password.py`: при включённой почте —
  отправка письма и нейтральное подтверждение без ссылки.
- [x] 4.3 `app/tutor/views/remember_password.py`: сбой доставки пишется в
  лог и не раскрывает существование аккаунта.
- [x] 4.4 `app/tutor/views/remember_password.py`: без SMTP — демо-режим со
  ссылкой на странице (поведение по умолчанию сохранено).

## 5. Тесты

- [x] 5.1 `tests/test_mail.py`: конфигурация (выключено по умолчанию,
  `mail_from`, ошибки старта, взаимоисключение SSL/STARTTLS, нулевые
  порт/таймаут).
- [x] 5.2 `tests/test_mail.py`: сборка письма (получатель, тема, отправитель,
  `Message-ID`, ссылка в HTML и тексте, fallback).
- [x] 5.3 `tests/test_mail.py`: отправка через подменённый `smtplib` —
  STARTTLS, SSL, без логина, ошибки SMTP и сети, проверки получателя/темы.
- [x] 5.4 `tests/test_password_reset_email.py`: получатель, тема, ссылка в
  обеих частях, срок из `TTL`, возврат ошибок транспорта.
- [x] 5.5 `tests/test_remember_password.py`: режим с почтой — письмо уходит,
  ссылки на странице нет; неизвестный email — письма нет; сбой не
  раскрывает аккаунт; ссылка от `APP_BASE_URL` и от адреса запроса.
- [x] 5.6 Прогон `tests/test_mail.py`, `tests/test_password_reset_email.py`,
  `tests/test_remember_password.py`, `tests/test_reset_password.py`,
  `tests/test_password_reset_service.py` и полного набора.

## 6. Документация

- [x] 6.1 `README.md`: строки `SMTP_*` и `APP_BASE_URL` в таблице
  «Конфигурация» и раздел «Как включить отправку почты (SMTP)».
- [x] 6.2 `CHANGELOG.md`: запись в `[Unreleased]` / «Добавлено».
- [x] 6.3 `openspec/specs/email/spec.md`: новая спека отправки почты.
- [x] 6.4 `openspec/specs/tutor-password-reset/spec.md`: требование запроса
  восстановления переписано под письмо и демо-режим.
- [x] 6.5 `openspec/changes/add-smtp-email/`: `proposal.md`, `design.md`,
  `tasks.md`, дельта `specs/`.
