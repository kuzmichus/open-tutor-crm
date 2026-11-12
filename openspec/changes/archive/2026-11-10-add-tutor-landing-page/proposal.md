# Proposal

## Why

Публичная часть лендинга уже отдаётся с `/` (change `add-landing-public`),
но создать и опубликовать страницу пока нечем: нет шаблона, нет страницы
управления и нет действий «опубликовать / снять / вернуть шаблон». Репетитор
не может получить лендинг из своего профиля, а пункт меню, через который он
попадал бы на страницу, отсутствует.

Задача закрывает этот разрыв: из профиля генерируется готовый черновик со
всеми точками входа, страница управления показывает состояние и выполняет
действия, а сайдбар в сингл-режиме получает пункт «Лендинг».

## What Changes

- Новый самодостаточный шаблон `app/landing/templates/default_page.html.j2`:
  inline-CSS, без CDN и `app.css`; шапка с входами ученика и родителя,
  hero с CTA «Записаться на занятие» → `/s/<tutor_id>`, секции «О себе»,
  «Стоимость», «Контакты», подвал с ненавязчивой ссылкой «вход» для
  репетитора, мобильный брейкпоинт, тег `/static/landing-auth.js`.
- Новый сервис `app/landing/services/template.py`: сборка контекста из
  `Tutor`, форматирование ставки, рендер и сохранение черновика
  (`save_default_draft`), состояние страницы (`page_state`).
- Новые вьюхи `app/landing/views/page.py`: `GET /tutor/landing`,
  `GET /tutor/landing/preview`, `POST /tutor/landing/publish|unpublish|reset`.
  Все роуты отвечают 404 в мульти-режиме.
- Новый шаблон страницы управления `app/landing/templates/landing/page.html`:
  статус, предпросмотр, публикация, снятие, возврат шаблона с подтверждением.
- Сайдбар: пункт «Лендинг» перед «Настройками», видимый только в
  сингл-режиме (`landing_enabled()` — Jinja-global).
- `app/templating.py`: каталог шаблонов модуля лендинга и регистрация
  `landing_enabled`.
- Тесты `tests/test_landing_page.py` и обновление `tests/test_sidebar.py`.
- Документация: раздел «Лендинг» в README, `CHANGELOG.md`, спека
  `landing-page`; на стенде включается `SINGLE_MODE=true`.

**Вне области:**

- Визуальный редактор GrapesJS и роут `/tutor/landing/editor` — отдельная
  задача; кнопка «Редактировать» скрыта до его появления.
- Клиентская подмена ссылок входов по факту авторизации
  (`/static/landing-auth.js`) — отдельная задача; тег в шаблоне уже стоит.
- Загрузка картинок из интерфейса и хранение в S3/БД.

## Capabilities

### New Capabilities

— (нет; расширяется существующая `landing-page`)

### Modified Capabilities

- `landing-page`: шаблон по умолчанию, страница управления, предпросмотр,
  действия со страницей и видимость пункта меню в сингл-режиме.

## Impact

- `app/landing/templates/*`, `app/landing/services/template.py`,
  `app/landing/views/page.py`, `app/landing/views/__init__.py`.
- `app/templating.py`, `app/templates/sidebar.html`.
- `tests/test_landing_page.py`, `tests/test_sidebar.py`.
- `.taskdesk/stand.toml` (`SINGLE_MODE=true`).
- Схема БД и миграции не меняются.
