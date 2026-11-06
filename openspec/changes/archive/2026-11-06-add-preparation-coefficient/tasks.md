# Tasks

## 1. Модель и миграция

- [x] 1.1 В `app/tutor/models/tutor_settings.py` объявить константы
  `DEFAULT_PREPARATION_COEFFICIENT = Decimal("0.70")` и
  `PREPARATION_COEFFICIENT_MAX = Decimal("5")`, ключ `preparation_coefficient` в
  `DEFAULTS` и колонку `Numeric(4, 2)`, NOT NULL с ORM-дефолтом.
- [x] 1.2 Создать ревизию `5eb0e460963e_add_preparation_coefficient.py`
  (`down_revision = '5b38b6d8c1a1'`): upgrade — `op.add_column` с
  `server_default='0.7'`, downgrade — `op.drop_column`. Проверка:
  `uv run alembic upgrade head`, `uv run alembic check` — чисто.

## 2. Сервисы, вьюха, шаблон

- [x] 2.1 `app/common/services/forms.py`: общий парсер `decimal_or_none`
  (запятая как разделитель, `NaN`/`Infinity` отбрасываются).
- [x] 2.2 `app/tutor/services/calendar_form.py`: разбор
  `preparation_coefficient` (пусто → 0.7, иначе число 0..5, иначе ошибка).
- [x] 2.3 `app/tutor/services/profile_page.py`: `preparation_coefficient` в ветке
  `# calendar` (Decimal без хвостовых нулей, «0.7»).
- [x] 2.4 `app/tutor/views/profile_calendar.py`: параметр формы и ключ в
  `dict form`.
- [x] 2.5 `app/tutor/templates/tutor/_tab_calendar.html`: карточка «Желаемая
  нагрузка» на `.form-grid` из двух полей, поле `type=number` (`min=0`,
  `max=5`, `step=0.1`) и пояснение красивой фразой.

## 3. Тесты

- [x] 3.1 `tests/test_profile.py`: `preparation_coefficient` в
  `_calendar_payload` и `_calendar_values`.
- [x] 3.2 Тесты дефолта, показа поля, сохранения и повторного показа, запятой,
  пустого поля и ошибок вне диапазона.
- [x] 3.3 Проверки `weekly_load_hours` не зависят от отступов разметки
  (регулярка по `name` + `value`).
- [x] 3.4 Полный прогон `uv run pytest -n auto`, линт ruff, `alembic check`.

## 4. Спецификация и документация

- [x] 4.1 Delta-spec `tutor-profile-settings`: блок «Желаемая нагрузка» из двух
  полей, правила валидации коэффициента. Проверка:
  `openspec validate add-preparation-coefficient --strict`.
- [x] 4.2 `CHANGELOG.md`: строка в `[Unreleased] → Добавлено`.