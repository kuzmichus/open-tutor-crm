# Tasks

## 1. Модель и миграция

- [x] 1.1 В `app/student/models/student.py` добавить импорт `date` и `Date`, объявить
  `birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)` рядом с `grade`.
  Проверка: `uv run pytest tests/test_models.py` — зелёный.
- [x] 1.2 Создать ревизию `ea9ed99a62d2_add_student_birth_date.py`
  (`down_revision = '10c3311d3321'`): upgrade — `op.add_column('students',
  sa.Column('birth_date', sa.Date(), nullable=True))`, downgrade — `op.drop_column`.
  Проверка: `uv run alembic upgrade head` и `alembic downgrade -1` на копии БД.

## 2. Сервисы

- [x] 2.1 `app/student/services/student_form.py`: добавить `birth_date` в `_TEXT_FIELDS`
  и разобрать значение (`date.fromisoformat`, пусто → None, `ValueError` → ошибка
  «Дата рождения указана некорректно.»). Ограничение «только ребёнок» не применять.
  Проверка: `tests/test_student_services.py` — разбор валидной, пустой и мусорной даты.
- [x] 2.2 `app/student/services/student_writer.py`: добавить `birth_date` в
  `_STUDENT_FIELDS` (в `_EMPTY_TO_NONE` не добавлять). Проверка: создание и очистка даты.
- [x] 2.3 `app/student/services/presentation.py`: `student_to_form` → ISO-строка,
  `empty_student_form` → `""`, `form_from_data` → приведение `date` к ISO;
  хелпер `birth_date_label` (`%d.%m.%Y`) и его регистрация в `register_template_helpers`.
  Проверка: повторная отрисовка формы после ошибки сохраняет выбранную дату.

## 3. Шаблоны

- [x] 3.1 `app/student/templates/student/_form.html`: поле «Дата рождения»
  (`input type="date"`, `name="birth_date"`) внутри fieldset «Общее» после Email,
  без `data-depends-on-kind`. Проверка: `tests/test_students_form.py`.
- [x] 3.2 `app/student/templates/student/card.html`: строка «Дата рождения» в блоке
  «Данные ученика» через `birth_date_label`. Проверка: карточка показывает `17.05.2012`.

## 4. Тесты

- [x] 4.1 `tests/test_models.py`: `birth_date is None` у минимальной карточки,
  сохранение даты в полной карточке.
- [x] 4.2 `tests/test_student_services.py`: разбор ISO/пусто/мусор, дата у взрослого,
  запись и очистка через `create_student`/`update_student`; в payload'ах добавлен
  `birth_date`.
- [x] 4.3 `tests/test_students_pages.py`: `_create_payload` содержит `birth_date`;
  тесты сохранения, очистки, ошибки валидации и показа даты в карточке.
- [x] 4.4 `tests/test_students_form.py`: `birth_date` в списке полей формы; тест, что
  поле — `type="date"` и не зависит от подтипа.
- [x] 4.5 `tests/test_timezone_select.py`: `_create_payload` дополнен `birth_date`.
- [x] 4.6 Полный прогон `uv run pytest -n auto` — падает только
  `tests/test_finance_invoice.py::test_invoice_dialog_opens_with_default_period`
  (воспроизводится без изменений задачи — тест зависит от текущей даты);
  линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py` — чисто.

## 5. Спецификация

- [x] 5.1 Change `add-student-birth-date` с delta-spec на `student-records`: дата
  рождения в «Составе карточки ученика» и требование «Дата рождения ученика».
  Проверка: `openspec validate add-student-birth-date --strict`.

## Workflow follow-up

- Строку «Ученики: дата рождения в карточке» добавить в `CHANGELOG.md` при следующем
  релизе (не отдельным коммитом).
- Синхронизировать и архивировать change после ревью.
