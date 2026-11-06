# Tasks

## 1. Модель и миграция

- [x] 1.1 В `app/tutor/models/tutor_settings.py` объявить
  `weekly_load_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)`,
  ключ `"weekly_load_hours": None` в `DEFAULTS` и константу
  `WEEKLY_LOAD_MAX_HOURS = 168`.
- [x] 1.2 Создать ревизию `5b38b6d8c1a1_add_tutor_weekly_load.py`
  (`down_revision = '7ce02b7b728c'`): upgrade — `op.add_column('tutor_settings',
  sa.Column('weekly_load_hours', sa.Integer(), nullable=True))`, downgrade —
  `op.drop_column`. Проверка: `uv run alembic upgrade head`,
  `uv run alembic check` — чисто.

## 2. Сервисы, вьюха, шаблон

- [x] 2.1 `app/tutor/services/calendar_form.py`: разбор `weekly_load_hours`
  (пусто → None, иначе целое 1..168, иначе ошибка). Импорт
  `WEEKLY_LOAD_MAX_HOURS`.
- [x] 2.2 `app/tutor/services/profile_page.py`: `weekly_load_hours` в ветке
  `# calendar` функции `_form_defaults` (пустая строка для NULL).
- [x] 2.3 `app/tutor/views/profile_calendar.py`: параметр `weekly_load_hours` в
  форме и `dict form`.
- [x] 2.4 `app/tutor/templates/tutor/_tab_calendar.html`: карточка «Желаемая
  нагрузка» с полем `type=number` и пояснением; без новых CSS-классов.

## 3. Тесты

- [x] 3.1 `tests/test_profile.py`: `weekly_load_hours` в `_calendar_values`;
  разбор валидного, пустого и некорректного значения.
- [x] 3.2 `tests/test_profile.py`: дефолт None, поле и пояснение на вкладке,
  сохранение и повторный показ, очистка пустым полем, ошибка вне диапазона,
  изоляция от другого репетитора.
- [x] 3.3 Полный прогон `uv run pytest -n auto`, линт ruff, `alembic check`.

## 4. Спецификация и документация

- [x] 4.1 Delta-spec `tutor-profile-settings`: пять блоков вкладки «Календарь»,
  поле желаемой нагрузки и правила валидации. Проверка:
  `openspec validate add-tutor-weekly-load --strict`.
- [x] 4.2 `CHANGELOG.md`: строка в `[Unreleased] → Добавлено`.