# Tasks

## 1. Общие сервисы ДЗ

- [x] 1.1 `app/homework/services/by_lesson.py`: `HIDDEN_STATUSES`,
  `homework_by_lesson(db, lesson_ids)` — один SELECT, пустой список даёт `{}`.
- [x] 1.2 `app/homework/services/presentation.py`: карты чипов и значков,
  `homework_status_label`, `homework_chip_class`, `homework_badge_class`,
  `homework_badge_label`, `register_template_helpers`.
- [x] 1.3 `app/templating.py`: регистрация хелперов ДЗ.
- [x] 1.4 Кабинет переходит на общие сервисы: `cabinet/services/calendar.py`,
  `homework.py`, `child_homework.py`, `presentation.py`; поведение прежнее.

## 2. Календарь

- [x] 2.1 `ScheduleEvent.homework_status` и необязательный аргумент
  `from_lesson`.
- [x] 2.2 `build_week_days`: `homework_by_lesson` один раз на неделю, статус
  передаётся в событие.
- [x] 2.3 `_lesson_fields`: `homework_status` и `homework_label`;
  `_slot_fields` — пустые значения.
- [x] 2.4 `calendar/_area.html`: `.cal-event__head`, значок
  `.cal-hw-badge {{ homework_badge_class(...) }}` с иконкой `book-open`,
  `title`/`aria-label`, суффикс ДЗ в `title` карточки.
- [x] 2.5 `styles.css`: `.cal-event__head` и правило для имени внутри него.

## 3. Тесты

- [x] 3.1 `tests/test_calendar.py`: значки четырёх статусов, отсутствие значка
  для `not_assigned` и без записи ДЗ, `homework_status` в `build_week_days`,
  суффикс ДЗ в подсказке, статическая проверка CSS.
- [x] 3.2 `tests/test_cabinet_calendar.py` и `tests/test_homework.py`:
  импорты после переноса, скрытие `not_assigned`, один запрос на неделю.

## 4. Документация и проверки

- [x] 4.1 `README.md` — карточка урока календаря показывает значок ДЗ.
- [x] 4.2 `CHANGELOG.md` — запись в `[Unreleased] → Добавлено` с TOCRM-61.
- [x] 4.3 `uv run pytest -n auto`, `ruff`, `alembic check`, `uv lock --check`.
