# Tasks

## 1. Сервис недели ученика

- [x] 1.1 Новый `app/cabinet/services/calendar.py`: `student_week_lessons(db,
  student_id, monday, tutor)` — два SELECT (индивидуальные по `Lesson.student_id`,
  групповые через `GroupMember`) в окне `week_bounds(monday, tutor)`, без фильтра
  по статусу; подпись цели — «Урок» или название группы, цвет — цвет цели.
  Проверка: `tests/test_cabinet_calendar.py` — свои уроки, чужие не видны,
  прошедшие и проведённые на месте, окно недели `[пн, пн+7)`.
- [x] 1.2 Там же `homework_by_lesson(db, lesson_ids)` — один SELECT по
  `Homework.lesson_id IN (…)` со статусом ≠ `not_assigned`.
  Проверка: карта статусов, «Не задано» отсутствует, число запросов не растёт.
- [x] 1.3 Там же `student_calendar_context(db, student, tutor, monday)` — семь
  `ScheduleDay` → `build_calendar_context`; прошедшие уроки получают
  `var(--muted-foreground)` и `is_past`, цена обнуляется, отметки недоступности
  не передаются, в представление карточки кладутся `homework_status` и
  `homework_label`. Проверка: `is_past` у прошедшего и отсутствие у будущего,
  `price_label` пустой, `unavailable` пустой у всех дней.
- [x] 1.4 `app/cabinet/services/presentation.py`: `homework_badge_class(status)`
  (`cal-hw-badge--assigned|submitted|checked|not_done`, fallback — `assigned`) и
  `homework_badge_label(status)`; обе зарегистрированы в
  `register_template_helpers()`. Проверка: значок «Задано»/«Проверено» на странице.

## 2. Вьюха и шаблоны

- [x] 2.1 `app/cabinet/views/index.py`: параметр `?start=`, нормализация через
  `week_start` с fallback на текущую неделю, контекст календаря, фрагмент
  `cabinet/_lessons_calendar.html` при `HX-Request`. Карточка «Ближайшее занятие»
  остаётся (замечание администратора к плану): `upcoming_lessons` зовётся только
  для полной страницы. Проверка: `tests/test_cabinet_pages.py`.
- [x] 2.2 Новый `app/cabinet/templates/cabinet/_lessons_calendar.html`: панель
  `.cal-toolbar` (ссылки `?start=…` + `hx-target="#student-calendar"`, заголовок
  недели, бейдж зоны), `.cal-grid` с шапкой дней, колонкой времени и семью
  колонками. Четверти — пассивные `div.cal-slot`. Проверка: `cal-grid` и
  `10:00 – 11:00` на странице.
- [x] 2.3 Там же карточка урока: `cal-event cal-event--readonly` (+
  `cal-event--past`), интервал, «Урок»/название группы, значок ДЗ только при
  непустом статусе, `title`/`aria-label` со статусом. Никаких `hx-get`,
  `data-start-min`, `data-duration-min`. Проверка: тест read-only разметки.
- [x] 2.4 `app/cabinet/templates/cabinet/lessons.html`: таблица удалена, вставлена
  карточка `section.card.cabinet-calendar` с включением области календаря.
  Проверка: «Ближайшее занятие» и `cal-grid` в одном ответе.

## 3. CSS

- [x] 3.1 `app/static/styles.css`: `.cabinet-calendar` (переменные сетки,
  `max-height`, `overflow: hidden`), `.cabinet-calendar__area` (flex-контейнер
  скролла), `.cal-event--readonly` и его hover — курсор `default`, без подъёма и
  тени. Проверка: `tests/test_css_styles.py` — все классы из шаблонов описаны.
- [x] 3.2 Там же `.cal-hw-badge` и модификаторы статусов на токенах темы
  (`--muted-foreground`, `--status-regular-fg`, `--success`, `--destructive`).
  Проверка: `test_no_color_literals_outside_tokens` зелёный.

## 4. Тесты

- [x] 4.1 `tests/test_cabinet_pages.py`: «Мои уроки» проверяет карточку
  «Ближайшее занятие», сетку и время урока ученика, отсутствие урока другого
  ученика; групповой урок — по названию группы; прошедший урок — `cal-event--past`;
  пустая неделя — «На этой неделе уроков нет». Проверка: файл зелёный.
- [x] 4.2 Новый `tests/test_cabinet_calendar.py`: сервис (изоляция, окно недели,
  подписи, карта ДЗ, `is_past`, отсутствие цены и недоступности) и страница
  (read-only: нет `calendar.js`, `/tutor/`, `@click="openSlot"`,
  `data-start-min`; листание `?start=`; htmx-фрагмент без каркаса; значок по
  статусу; кривой `?start=`).

## 5. Спецификация и регресс

- [x] 5.1 Delta-spec `openspec/changes/add-student-lessons-calendar/specs/student-cabinet/spec.md`:
  требование «Кабинет: вкладка «Мои уроки»» переписано под календарь, добавлены
  «Карточка урока в календаре ученика», «Прошедший урок в календаре ученика»,
  «Недоступность репетитора скрыта от ученика» и «Значок домашнего задания в
  календаре». Проверка: `openspec validate add-student-lessons-calendar --strict`.
- [x] 5.2 Полный прогон `uv run pytest -n auto` — зелёный (кроме известного
  красного `tests/test_finance_invoice.py`, который падает и на базовой ветке).
- [x] 5.3 Линт `uvx ruff check --select E9,F63,F7,F82 app/ tests/ main.py` — без
  ошибок.

## Workflow follow-up

- Строку «Добавлено: недельный календарь в кабинете ученика (только чтение)» —
  в `CHANGELOG.md` при следующем релизе, не отдельным коммитом.
- Архивировать change после ревью (`openspec archive add-student-lessons-calendar`).
