# Tasks

## 1. Модель и миграция

- [x] 1.1 В `app/student/models/student.py` объявить
  `city: Mapped[str | None] = mapped_column(String(100), nullable=True)` перед `school`.
  Проверка: `uv run pytest tests/test_models.py` — зелёный.
- [x] 1.2 Создать ревизию `55b9846687b4_add_student_city.py`
  (`down_revision = 'a7d3e1f42b90'`): upgrade — `op.add_column('students',
  sa.Column('city', sa.String(length=100), nullable=True))`, downgrade — `op.drop_column`.
  Проверка: `uv run alembic upgrade head` и `uv run alembic check` — чисто.

## 2. Сервисы

- [x] 2.1 `app/student/services/student_form.py`: добавить `city` в `_TEXT_FIELDS`,
  константу `_CITY_MAX = 100` и проверку длины («Город не длиннее 100 символов.»).
  В сброс для взрослого город не добавлять. Проверка: разбор, обрезка пробелов, лимит.
- [x] 2.2 `app/student/services/student_writer.py`: `city` в `_STUDENT_FIELDS` и в
  `_EMPTY_TO_NONE` (пустое значение → NULL). Проверка: создание, изменение, очистка.
- [x] 2.3 `app/student/services/presentation.py`: `student_to_form` → `student.city or ""`,
  `empty_student_form` → `"city": ""`.
- [x] 2.4 Новый `app/student/services/cities.py`: `city_options(db, tutor_id,
  exclude_student_id=None)` и `city_options_json(...)` — города других учеников
  репетитора, дедупликация и сортировка по `casefold()`, пустой `label`.
- [x] 2.5 `app/student/services/form_context.py`: положить `city_options_json` в контекст
  формы, исключив город открытой карточки.

## 3. Шаблоны и ассеты

- [x] 3.1 `app/student/templates/student/_form.html`: поле «Город» — combobox
  (`name="city"`, `id="student-city"`, `data-options="{{ city_options_json }}"`)
  между «Классом» и «Школой», без `data-depends-on-kind`. Заметка в списке:
  «Ничего не найдено — город будет добавлен».
- [x] 3.2 `app/student/templates/student/_card.html`: город с иконкой `map-pin` в блоке
  контактов миникарточки; условие вывода блока расширено на `student.city`.
- [x] 3.3 `app/student/templates/student/card.html`: поле «Город» с иконкой в блоке
  «Данные ученика» перед «Школой», без проверки подтипа.
- [x] 3.4 `uv run python scripts/build_icons.py` — `map-pin` в наборе.
  Проверка: `uv run pytest tests/test_icons_bundle.py`.

## 4. Тесты

- [x] 4.1 `tests/test_models.py`: `city is None` у минимальной карточки, город в полной.
- [x] 4.2 `tests/test_student_services.py`: разбор и обрезка, пустое значение, лимит
  100 символов, город у взрослого, запись и очистка через `create_student`/`update_student`;
  во все payload'ы добавлен `city`.
- [x] 4.3 `tests/test_students_pages.py`: `city` в `_create_payload`, показ города в карточке.
- [x] 4.4 `tests/test_students_form.py`: `city` в списке полей; город идёт после класса и
  перед школой; поле — combobox с `data-options` и не зависит от подтипа; значение
  сохраняется при редактировании.
- [x] 4.5 `tests/test_students_ui.py`: город с иконкой в миникарточке (и у взрослого),
  город в большом профиле перед школой, отсутствие иконки без города.
- [x] 4.6 Новый `tests/test_student_city.py`: выборка только по своим ученикам, без
  пустых значений, дедупликация без учёта регистра, сортировка, исключение своего
  города, сохранение города вне списка, сохранение у взрослого, очистка.
- [x] 4.7 `tests/test_timezone_select.py`: `city` в payload; хелпер `data-options`
  привязан к блоку поля часового пояса (на странице два combobox).
- [x] 4.8 Полный прогон `uv run pytest -n auto` — 2120 passed; линт
  `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py` — чисто.

## 5. Спецификация

- [x] 5.1 Change `add-student-city` с delta-spec на `student-records`: город в
  «Составе карточки ученика» и требование «Город ученика».
  Проверка: `openspec validate add-student-city --strict`.

## Workflow follow-up

- Строка «Ученики: город в карточке и подсказки городов» добавлена в `CHANGELOG.md`,
  секция `[Unreleased] → Добавлено` — вместе с change'ем, по конвенции проекта.
- Синхронизировать и архивировать change после ревью.
