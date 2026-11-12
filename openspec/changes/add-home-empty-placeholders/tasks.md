# Tasks

## 1. Разметка заглушек

- [x] 1.1 `app/tutor/templates/tutor/home.html`: блок «Расписание на сегодня»
  — заглушка с иконкой `calendar`, заголовком «Нет запланированных уроков» и
  подсказкой «Добавьте урок в календаре».
- [x] 1.2 Блок «Недавние платежи» — иконка `credit-card`, «Нет платежей»,
  «Платежи появятся здесь».
- [x] 1.3 Иконки помечены `aria-hidden="true"` — они декоративные.

## 2. Стили

- [x] 2.1 `.home-empty` — центрированная колонка с `min-height`, чтобы блок не
  «схлопывался» при появлении списка.
- [x] 2.2 `.home-empty__icon` (32×32, приглушение), `.home-empty__title`,
  `.home-empty__text` — на токенах темы, без литеральных цветов.
- [x] 2.3 Проверить, что новые классы описаны в `styles.css`
  (`tests/test_css_styles.py`).

## 3. Тесты

- [x] 3.1 `tests/test_home.py::test_dashboard_empty_blocks_have_placeholder`:
  иконка, заголовок и подсказка в своей панели.
- [x] 3.2 `tests/test_home.py::test_dashboard_filled_blocks_hide_placeholder`:
  при наличии урока и платежа заглушек нет.
- [x] 3.3 Обновить `test_dashboard_isolation` под новые подписи пустых блоков.

## 4. Документация

- [x] 4.1 `openspec/specs/tutor-dashboard/spec.md`: требование заглушек и
  сценарии пустых блоков.
- [x] 4.2 `openspec/changes/add-home-empty-placeholders/`: proposal, design,
  tasks, delta-спека, `.openspec.yaml`.
- [x] 4.3 `CHANGELOG.md`: запись в `[Unreleased]`.
