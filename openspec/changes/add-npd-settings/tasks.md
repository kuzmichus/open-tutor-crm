# Tasks

## 1. Модель и миграция

- [x] 1.1 В `app/tutor/models/tutor_settings.py` объявить константы
  `DEFAULT_NPD_ENABLED = False`,
  `DEFAULT_NPD_TAX_RATE_INDIVIDUAL = Decimal("4.00")`,
  `DEFAULT_NPD_TAX_RATE_LEGAL_ENTITY = Decimal("6.00")`,
  `DEFAULT_NPD_ANNUAL_INCOME_LIMIT = 2_400_000`, `NPD_TAX_RATE_MAX = Decimal("100")`,
  ключи в `DEFAULTS` и четыре колонки `TutorSettings` (`npd_enabled`,
  `npd_tax_rate_individual`, `npd_tax_rate_legal_entity`,
  `npd_annual_income_limit`).
- [x] 1.2 Создать ревизию `b7d24c9e5f10_add_npd_tax_settings.py`
  (`down_revision = 'c3f1a9d7e2b4'`): upgrade — четыре `op.add_column` с
  `server_default`, downgrade — `op.drop_column` в обратном порядке. Проверка:
  `uv run alembic upgrade head`, `uv run alembic check` — чисто.

## 2. Сервисы и вьюха

- [x] 2.1 `app/tutor/services/finances_form.py`: `parse_finances_form(form) ->
  (values | None, errors)` — переключатель через `checked`, ставки через
  `decimal_or_none` (0..100, запятая допустима, пусто → дефолт), лимит через
  `int_or_none` (пробелы внутри числа допустимы, пусто → 2 400 000, иначе ≥ 0).
- [x] 2.2 `app/tutor/views/profile_finances.py`: POST `/tutor/profile/finances`
  (по образцу `profile_calendar.py`); при ошибках — ре-рендер вкладки с
  введёнными значениями, иначе `save_settings` и 303 на
  `/tutor/profile?tab=finances&saved=1`.
- [x] 2.3 Регистрация роутера в `app/tutor/views/__init__.py`.

## 3. Вкладка и шаблон

- [x] 3.1 `app/tutor/services/profile_page.py`: `("finances", "Финансы")` в
  `TABS`, адрес в `TAB_ACTIONS`, ветка `finances` в `_form_defaults` (Decimal
  без хвостовых нулей, лимит строкой).
- [x] 3.2 `app/tutor/templates/tutor/_tab_finances.html`: карточка «Налоги» —
  переключатель НПД, `.form-grid` из двух полей ставок с подписями
  `.card__desc`, отдельное поле годового лимита, кнопка «Сохранить». Новых
  CSS-классов не вводить.
- [x] 3.3 `app/tutor/templates/tutor/profile.html`: ветка `tab == 'finances'`,
  подзаголовок страницы с «Финансами».
- [x] 3.4 `app/tutor/views/profile.py`: докстринг «пять вкладок».

## 4. Тесты

- [x] 4.1 Новый `tests/test_profile_finances.py`: доступ без сессии, наличие и
  активность вкладки, состав блока «Налоги», дефолты до первого сохранения,
  сохранение и повторный показ, запятая в ставке, сумма с пробелами, пустые
  поля, выключенный переключатель, ошибки вне диапазона и мусор, сохранение
  введённых значений при ошибке, границы 0 и 100, изоляция между репетиторами,
  разбор формы без HTTP.
- [x] 4.2 `tests/test_profile.py`: `test_all_tabs_present` (вкладка `finances`),
  новый подзаголовок страницы.
- [x] 4.3 Полный прогон `uv run pytest -n auto`, линт ruff, `alembic check`.

## 5. Спецификация и документация

- [x] 5.1 Delta-spec `tutor-profile-settings`: пятая вкладка «Финансы» и
  требование к блоку «Налоги» с дефолтами и правилами валидации. Проверка:
  `openspec validate add-npd-settings --strict`.
- [x] 5.2 `CHANGELOG.md`: строка в `[Unreleased] → Добавлено`.
