# Tasks

## 1. Модель и миграция

- [x] 1.1 `app/student/models/student.py`: добавить константу
  `STUDENT_PAYER_TYPES = ("individual", "legal_entity")` рядом с
  `STUDENT_KINDS`/`STUDENT_STATUSES`, колонку
  `payer_type: Mapped[str]` (`String(16)`, `nullable=False`,
  `default="individual"`, `server_default="individual"`) и
  `CheckConstraint("payer_type IN ('individual', 'legal_entity')",
  name="ck_students_payer_type")` в `__table_args__`.
- [x] 1.2 `alembic/versions/c3f1a9d7e2b4_add_student_payer_type.py`:
  `down_revision = '5eb0e460963e'` (после влитой TOCRM-41 — иначе получаются
  две головы и `alembic upgrade head` падает), `op.add_column` с NOT NULL,
  `server_default='individual'` и CHECK в самой колонке; откат —
  `op.drop_column('students', 'payer_type')`. Проверка:
  `alembic upgrade head` на чистой SQLite.

## 2. Сервисы

- [x] 2.1 `app/student/services/student_form.py`: читать `payer_type` из формы
  (`text_value(form, "payer_type") or "individual"`) и отклонять значение вне
  `STUDENT_PAYER_TYPES` сообщением «Выберите тип плательщика: физлицо или
  юрлицо.», подставляя безопасный дефолт.
- [x] 2.2 `app/student/services/presentation.py`: `payer_type` в
  `student_to_form` (с fallback `individual`), `empty_student_form` и
  `form_from_data`; словарь `_PAYER_TYPE_LABELS` и функция
  `payer_type_label`; регистрация хелпера в `register_template_helpers()`.
- [x] 2.3 `app/student/services/student_writer.py`: записывать
  `data.get("payer_type") or "individual"` в `_apply_student_fields` — так
  прямые вызовы `create_student`/`update_student` без ключа не падают.

## 3. Шаблоны

- [x] 3.1 `app/student/templates/student/_form.html`: в секции «Плательщик»
  под полем «Кто оплачивает занятия» добавить радиогруппу `.tabs tabs--radio`
  с `role="radiogroup"`, `aria-labelledby="payer-type-label"` и radio
  `name="payer_type"` (`individual` — отмечено по умолчанию, `legal_entity` —
  по `form.payer_type`). Подсветку выбранного сегмента даёт CSS, а не Alpine.
- [x] 3.2 `app/static/styles.css`: правило
  `.tabs--radio .tab:has(input:checked)` — фон, цвет и тень активного таба для
  радиогрупп без Alpine-модели (приём `.un-modes__option`).
- [x] 3.3 `app/student/templates/student/card.html`: под ФИО плательщика
  вывести `{{ payer_type_label(student.payer_type) }}`.

## 4. Тесты

- [x] 4.1 `tests/test_models.py`: тип по умолчанию `individual`; значение вне
  пары отклоняется CHECK-ограничением.
- [x] 4.2 `tests/test_student_services.py`: парсинг дефолта и допустимого
  значения, ошибка на неизвестном; `create_student`/`update_student`
  сохраняют тип; вызов без ключа даёт `individual`.
- [x] 4.3 `tests/test_students_form.py`: поле `payer_type` есть в форме;
  переключатель стоит в секции плательщика после селекта; по умолчанию
  отмечено «Физлицо»; в форме редактирования отмечено сохранённое значение;
  выбранный сегмент подсвечивается CSS-правилом `.tabs--radio`.
- [x] 4.4 `tests/test_students_pages.py`: создание и редактирование с
  `payer_type`, дефолт без поля, ошибка на неизвестном значении, подпись
  «Юрлицо» в карточке.
- [x] 4.5 `tests/test_migration_heads.py`: у цепочки ревизий ровно одна
  голова, revision id не повторяются, нет merge-ревизий с двумя родителями —
  иначе `alembic upgrade head` в `.taskdesk/stand-up.sh` не выполнится.

## 5. Регресс и документация

- [x] 5.1 `uv run pytest -n auto` — весь набор зелёный.
- [x] 5.2 Линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/
  main.py cron.py` — без ошибок.
- [x] 5.3 `CHANGELOG.md`: строка в `## [Unreleased]` о переключателе
  «Физлицо / Юрлицо» рядом с выбором плательщика.
- [x] 5.4 OpenSpec: change `add-student-payer-type` (proposal, design, tasks,
  delta-specs `student-records` и `student-contacts`); `openspec validate`
  зелёный.

## Workflow follow-up

- Архив change'а — после ревью (`openspec archive add-student-payer-type`).
