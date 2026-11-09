# Tasks

## 1. Вендоринг и локаль

- [x] 1.1 `app/static/dist/grapesjs/`: `grapes.min.js`,
  `grapes.min.css`, `LICENSE` из npm-пакета `grapesjs@0.23.9`.
- [x] 1.2 `README.md` рядом с файлами: версия, дата, источник,
  контрольные суммы, фактическая лицензия BSD-3-Clause, порядок обновления.
- [x] 1.3 `.gitignore`: исключения `!app/static/dist/` и
  `!app/static/dist/**` после глобального `dist/`.
- [x] 1.4 `i18n-ru.js`: `window.grapesjsI18nRu` по структуре
  `locale/en.js` — ассеты, блоки, устройства, панели, селекторы, стили,
  трейты, компоненты, хранилище, код.

## 2. Сервис черновика

- [x] 2.1 `draft_render.py`: `extract_body`, `extract_first_style`,
  `extract_title`, `strip_scripts`, `default_title`, `build_document`,
  `ensure_auth_script`, `render_draft_document`.
- [x] 2.2 Снятие обёртки `<body>` от `editor.getHtml()` и идемпотентный
  тег `landing-auth.js`.

## 3. Вьюхи и шаблон

- [x] 3.1 `views/editor.py`: `GET /tutor/landing/editor`,
  `POST /tutor/landing/draft`, 404 в мульти-режиме, сессия репетитора,
  автосоздание черновика, `Cache-Control: no-store`.
- [x] 3.2 `views/__init__.py`: подключить роутер редактора.
- [x] 3.3 `templates/landing/editor.html`: автономный документ, верхняя
  панель, контейнер `#gjs`, локальный GrapesJS и `i18n-ru.js`, JSON
  черновика, инициализация с русской локалью и `storageManager: none`,
  сохранение через fetch, `getCss({ avoidProtected: true })` и замена
  `#wrapper` → `body`.
- [x] 3.4 `views/page.py` и `templates/landing/page.html`: кнопка
  «Редактировать» видна всегда и ведёт в редактор.

## 4. Тесты

- [x] 4.1 `tests/test_landing_editor.py`: доступ, 404 в мульти-режиме,
  автосоздание, автономность страницы, извлечение тела/CSS, сохранение,
  title, идемпотентность тега, круглый трип, кнопка управления,
  вендоринг.
- [x] 4.2 Unit-тесты `draft_render`: тело, стиль, title, скрипты, сборка
  документа, снятие обёртки body, default title.

## 5. Документация и проверка

- [x] 5.1 `README.md`: описание редактора, локали и вендоринга.
- [x] 5.2 `CHANGELOG.md`: пункт в `[Unreleased] → Добавлено`.
- [x] 5.3 `openspec/changes/add-landing-editor/`: proposal, design,
  tasks, delta-спека, `.openspec.yaml`.
- [x] 5.4 `openspec/specs/landing-page/spec.md`: требования редактора,
  локали, вендоринга, разбора/сборки и тега `landing-auth.js`; кнопка
  «Редактировать» больше не скрыта.
- [x] 5.5 Прогон `tests/test_landing_editor.py` и соседних тестов
  лендинга; ручная проверка редактора на стенде.
