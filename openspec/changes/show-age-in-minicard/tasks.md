# Tasks

## 1. Расчёт полных лет

- [x] 1.1 `app/student/services/birthdays.py`: добавить
  `full_years(birth_date: date, day: date) -> int | None` — разница годов минус
  1, если день рождения в текущем году ещё не наступил; `None`, если дата
  рождения в будущем. `age_on` не менять. Проверка:
  `uv run pytest tests/test_student_age.py`.
- [x] 1.2 Зафиксировать в docstring `full_years` правило 29 февраля: в
  невисокосные годы полные годы прибавляются 1 марта (сравнение кортежей
  `(month, day)`). Проверка: тест на рождение 29.02 в невисокосном году.

## 2. Подпись возраста

- [x] 2.1 `app/student/services/presentation.py`: вынести русскую плюрализацию
  лет в приватный `_years_label(age: int) -> str` («1 год» / «2 года» /
  «5 лет», 11–14 → «лет») и переписать через него `birthday_age_label` без
  изменения поведения. Проверка: `tests/test_birthday_digest.py` зелёный.
- [x] 2.2 `presentation.py`: добавить `student_age_label(birth_date, tutor) ->
  str` — «12 лет» по сегодняшней дате в зоне педагога (`today_local`) через
  `full_years`; пустая строка, если даты нет или она в будущем. Проверка:
  `tests/test_student_age.py`.
- [x] 2.3 `presentation.py`: зарегистрировать `student_age_label` в
  `register_template_helpers()` рядом с `birth_date_label`.

## 3. Шаблон

- [x] 3.1 `app/student/templates/student/_card.html`: заменить
  `{{ kind_label(student.kind) }}` на
  `{{ student_age_label(student.birth_date, tutor) or kind_label(student.kind) }}`,
  сохранив суффикс «, N класс». Новых CSS-классов не вводить. Проверка:
  `tests/test_students_ui.py`, `tests/test_css_styles.py`.
- [x] 3.2 Убедиться, что `tutor` передаётся во все рендеры `_card.html`
  (`views/index.py`, `views/list_partial.py`, `views/create_student.py`,
  `views/update_student.py`, `views/archive_student.py`) — правок во вьюхах не
  требуется.

## 4. Тесты

- [x] 4.1 Новый `tests/test_student_age.py`: `full_years` — ДР ещё не наступил,
  сегодня, уже прошёл в этом году, рождение 29.02 в невисокосном году, дата в
  будущем → `None`.
- [x] 4.2 `tests/test_student_age.py`: `student_age_label` — склонения «1 год»,
  «2 года», «5 лет», «11 лет», «21 год», «12 лет»; `None` и будущая дата → «».
- [x] 4.3 `tests/test_student_age.py`: часовой пояс — при моменте, когда в UTC
  ещё 2 ноября, а в `Europe/Ulyanovsk` уже 3-е, возраст у репетитора +04 на год
  больше при ДР 3 ноября.
- [x] 4.4 `tests/test_students_ui.py`: миникарточка с датой рождения показывает
  «7 лет» и не содержит «Ребёнок»; взрослый с датой — возраст вместо
  «Взрослый»; ребёнок с классом — «7 лет, 5 класс».
- [x] 4.5 `tests/test_students_ui.py`: ученик без даты рождения по-прежнему
  показывает «Ребёнок»/«Взрослый», дата в будущем — тоже подпись подтипа.

## 5. Регресс и документация

- [x] 5.1 `uv run pytest -n auto` — зелёными остаются
  `tests/test_birthday_digest.py`, `tests/test_students_ui.py`,
  `tests/test_students_pages.py`, `tests/test_css_styles.py`.
- [x] 5.2 Линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py`
  — без ошибок.
- [x] 5.3 `CHANGELOG.md`: строка в секцию `## [Unreleased]` — «В миникарточке
  ученика вместо подтипа показывается возраст полных лет, если указана дата
  рождения».

## Workflow follow-up

- Архив change'а — после ревью (`openspec archive show-age-in-minicard`).
