# Tasks

## 1. Шаблон и генерация черновика

- [x] 1.1 `app/landing/templates/default_page.html.j2`: самодостаточная
  страница (inline-CSS, без CDN и `app.css`), шапка с входами ученика и
  родителя, hero с CTA на `/s/<tutor_id>`, секции «О себе», «Стоимость»,
  «Контакты», подвал со ссылкой «вход», мобильный брейкпоинт,
  `<script src="/static/landing-auth.js" defer>`.
- [x] 1.2 Все поля профиля экранируются (`| e`), пустые секции не
  рендерятся.
- [x] 1.3 `app/landing/services/template.py`: `public_page_url`,
  `hourly_rate_label` («1 200 ₽»), `page_title`, `build_default_context`,
  `render_default_page`, `save_default_draft`, `page_state`.
- [x] 1.4 `app/templating.py`: каталог `app/landing/templates` в
  `TEMPLATE_DIRS`; регистрация `landing_enabled` в Jinja-globals.

## 2. Страница управления и действия

- [x] 2.1 `app/landing/views/page.py`: `_ensure_landing_enabled()` (404 в
  мульти-режиме) на каждом роуте, `_tutor_or_login`.
- [x] 2.2 `GET /tutor/landing`: статус, плашка по `?status=`,
  `editor_available=False`.
- [x] 2.3 `GET /tutor/landing/preview`: `FileResponse` черновика,
  `Cache-Control: no-cache`, 404 без черновика.
- [x] 2.4 `POST /tutor/landing/publish|unpublish|reset` → 303 со статусом.
- [x] 2.5 `app/landing/templates/landing/page.html`: карточка статуса с
  чипом, кнопки предпросмотра/публикации/снятия, «Вернуть шаблон» с
  двухшаговым подтверждением, «Создать черновик» в пустом состоянии,
  скрытая «Редактировать».
- [x] 2.6 `app/landing/views/__init__.py`: подключить роутер страницы.

## 3. Сайдбар

- [x] 3.1 `app/templates/sidebar.html`: пункт «Лендинг» перед «Настройками»
  под `{% if landing_enabled() %}`, иконка `globe`.
- [x] 3.2 `tests/test_sidebar.py`: пункт есть в сингл-режиме выше
  «Настроек» и активен на странице; в мульти-режиме пункта нет, роут 404.

## 4. Тесты

- [x] 4.1 `tests/test_landing_page.py`: доступ и 404 в мульти-режиме (в том
  числе при двух репетиторах), пустое состояние, генерация из профиля,
  экранирование, точки входа и отсутствие CDN, сохранность правок,
  предпросмотр, публикация с бэкапом, снятие, статусы страницы.

## 5. Документация и стенд

- [x] 5.1 `README.md`: абзацы «Управление» и «Редактор» в разделе «Лендинг».
- [x] 5.2 `CHANGELOG.md`: пункт в `[Unreleased] → Добавлено`.
- [x] 5.3 `openspec/specs/landing-page/spec.md`: требования шаблона,
  страницы управления, предпросмотра, действий и пункта меню.
- [x] 5.4 `openspec/changes/add-tutor-landing-page/`: proposal, design,
  tasks, delta-спека, `.openspec.yaml`.
- [x] 5.5 `.taskdesk/stand.toml`: `SINGLE_MODE = "true"` в `[stand.env]`.
