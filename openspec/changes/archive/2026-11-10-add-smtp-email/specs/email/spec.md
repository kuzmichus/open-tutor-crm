# Spec Delta

## ADDED Requirements

### Requirement: Отправка писем через SMTP

Система SHALL уметь отправлять письма через SMTP-сервер, заданный
конфигурацией. Письмо SHALL содержать HTML- и текстовую часть (UTF-8),
тему и адрес отправителя. Соединение SHALL использовать STARTTLS
(`SMTP_STARTTLS`) либо сразу TLS (`SMTP_USE_SSL`); авторизация SHALL
выполняться только при заданном `SMTP_USERNAME`.

#### Scenario: Письмо доставлено через STARTTLS

- **GIVEN** заданы `SMTP_HOST`, `SMTP_PORT=587`, `SMTP_USERNAME` и
  `SMTP_PASSWORD`, `SMTP_STARTTLS=true`
- **WHEN** сервис вызывает `send_email` с получателем, темой и HTML
- **THEN** клиент открывает соединение с сервером, выполняет STARTTLS,
  авторизуется и отправляет письмо `multipart/alternative`; возвращается
  пустой список ошибок

#### Scenario: Письмо через SSL

- **GIVEN** заданы `SMTP_HOST`, `SMTP_PORT=465`, `SMTP_USE_SSL=true`,
  `SMTP_STARTTLS=false`
- **WHEN** сервис вызывает `send_email`
- **THEN** соединение открывается по TLS сразу, STARTTLS не вызывается

#### Scenario: Ошибка доставки не бросается исключением

- **WHEN** почтовый сервер недоступен или отклоняет письмо
- **THEN** `send_email` возвращает непустой список строк с причиной, а
  приложение продолжает работу

### Requirement: Почта включается конфигурацией

Система SHALL считать почту включённой тогда и только тогда, когда задан
`SMTP_HOST`. При пустом `SMTP_HOST` отправка MUST NOT выполняться, а
`send_email` SHALL возвращать ошибку о ненастроенной почте. Адрес
отправителя SHALL браться из `SMTP_FROM`, а при его отсутствии — из
`SMTP_USERNAME`.

#### Scenario: Почта не настроена

- **GIVEN** `SMTP_HOST` пуст
- **WHEN** вызван `send_email`
- **THEN** возвращается ошибка «Отправка почты не настроена», соединение
  с SMTP не открывается

#### Scenario: Отправитель по умолчанию

- **GIVEN** `SMTP_HOST` и `SMTP_USERNAME` заданы, `SMTP_FROM` пуст
- **WHEN** собирается письмо
- **THEN** в поле `From` указан адрес из `SMTP_USERNAME`

### Requirement: Неполная конфигурация SMTP — ошибка старта

Если `SMTP_HOST` задан, приложение MUST NOT стартовать при отсутствии
отправителя (пустые `SMTP_FROM` и `SMTP_USERNAME`), при неположительных
`SMTP_PORT`/`SMTP_TIMEOUT` или при одновременных `SMTP_USE_SSL` и
`SMTP_STARTTLS`. Сообщение SHALL называть недостающие параметры.

#### Scenario: Нет отправителя

- **GIVEN** `SMTP_HOST` задан, `SMTP_FROM` и `SMTP_USERNAME` пусты
- **WHEN** приложение загружает конфигурацию
- **THEN** возникает ошибка с упоминанием `SMTP_FROM` и `SMTP_USERNAME`

#### Scenario: Одновременно SSL и STARTTLS

- **GIVEN** `SMTP_USE_SSL=true` и `SMTP_STARTTLS=true`
- **WHEN** приложение загружает конфигурацию
- **THEN** возникает ошибка о взаимоисключающих параметрах

### Requirement: Внешний адрес приложения для ссылок в письмах

Система SHALL использовать `APP_BASE_URL` как базу абсолютных ссылок в
письмах. При пустом значении база SHALL строиться из адреса запроса.

#### Scenario: Ссылка за прокси

- **GIVEN** `APP_BASE_URL=https://crm.example.com`
- **WHEN** формируется ссылка восстановления пароля
- **THEN** ссылка начинается с `https://crm.example.com/`
