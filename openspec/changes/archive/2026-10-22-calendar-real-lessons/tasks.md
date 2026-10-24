# Tasks

## 1. Палитра и цвет цели

- [x] 1.1 Создать `app/common/colors.py` с палитрой из 16 разнесённых hex-цветов и функцией `assign_color(db, tutor_id)`, выбирающей свободный цвет из палитры по занятым `students.color` + `groups.color` репетитора; покрыть тестом: цвет не совпадает с уже занятыми, при исчерпании палитры возвращается цвет из полной палитры (`tests/test_colors.py` новый, `uv run pytest tests/test_colors.py`)
- [x] 1.2 Добавить миграцию `alembic revision --autogenerate -m "add target color"`: колонки `students.color`, `groups.color` (`String(7)`, nullable) с data-migration бэкфилом существующих строк по `tutor_id` через `assign_color`; проверить `uv run alembic upgrade head` и `uv run alembic downgrade -1` проходят без ошибок
- [x] 1.3 Вызывать `assign_color` при создании ученика в `app/student/services/student_writer.py::create_student`; проверить новым тестом: созданный ученик имеет непустой цвет из палитры (`tests/test_student_services.py`)
- [x] 1.4 Вызывать `assign_color` при создании ученика мини-формой `app/group/services/student_mini.py::create_student` и при создании группы в `app/group/services/group_writer.py::create_group`; проверить тестами: мини-форма и группа получают цвет (`tests/test_lesson_lookup.py`, `tests/test_group_services.py`)
- [x] 1.5 Убедиться, что редактирование ученика и группы (`update_student`, `update_group`) не меняет цвет; тест: после обновления полей цвет прежний (`tests/test_student_services.py`, `tests/test_group_services.py`)

## 2. Недельная выборка уроков и рендер карточек

- [x] 2.1 Создать `app/calendar/services/week.py` с `week_lessons(db, tutor_id, monday)`: JOIN-изоляция по цели (`or_(Student.tutor_id, Group.tutor_id)`), окно `[monday, monday+7)` по `starts_at`; тест: возвращаются только уроки репетитора и только запрошенной недели, чужие не попадают (`tests/test_calendar.py`)
- [x] 2.2 Расширить `app/calendar/services/schedule_event.py`: поля `lesson_id`, `status`, `is_completed` + конструктор `from_lesson(lesson, *, target_name, target_id, target_color)`; тест: событие из строки БД несёт id урока, цель, статус и цвет (`tests/test_calendar.py`)
- [x] 2.3 Подключить `week_lessons` в `app/calendar/views/index.py`, собрав `ScheduleEvent` из уроков БД вместо `demo_schedule.build_week`; демо-отпуск оставить прежним источником; тест: сетка недели содержит реальные уроки репетитора с `data-lesson-id` (`tests/test_calendar.py`)
- [x] 2.4 Перенести позиционирование/наложение из `presentation.py` на смешанный список (уроки БД + демо-отпуск); проверить, что `layout_events` накладывает пересекающиеся реальные уроки и `is_past` приглушает прошедшие; тесты на наложение и `is_past` для реальных уроков (`tests/test_calendar.py`)
- [x] 2.5 Вычислять «просрочен» на сервере (`status == 'planned'` и `starts_at + duration < now`) и прокидывать в контекст; тест: просроченный урок отличается от запланированного и проведённого (`tests/test_calendar.py`)
- [x] 2.6 Обновить шапку дней (точки и счётчик) и пустое состояние под реальные уроки; тесты: счётчик со склонением по реальным урокам, пустая неделя показывает пояснение (`tests/test_calendar.py`)

## 3. Диалоги создания и редактирования на календаре

- [x] 3.1 Добавить `GET /tutor/lessons/new?starts_at=` с префиллом начала: параметр заполняет поле «Начало», некорректное значение открывает пустую форму; тесты: корректный и кривой префилл (`tests/test_lesson_create.py`)
- [x] 3.2 Подключить `lessons.js` на страницу календаря до `alpine.min.js` и добавить `<div id="modal">` вне `#calendar-swap`; тест: `lessons.js` подключён до alpine, контейнер присутствует и вне области свопа (`tests/test_calendar.py`)
- [x] 3.3 Повесить на карточку урока `hx-get="/tutor/lessons/{id}/edit"` с `hx-target="#modal"`, `data-lesson-id`; демо-события (отпуск, слоты) атрибут не получают; тест: карточка урока несёт edit-ссылку, карточка отпуска — нет (`tests/test_calendar.py`)
- [x] 3.4 Заменить кнопку «Добавить» и клик по пустой четверти на открытие `GET /tutor/lessons/new` с префиллом даты/времени четверти (кнопка «Добавить» — ближайшая будущая четверть); тест разметки: entry-точки ведут на `/tutor/lessons/new` (`tests/test_calendar.py`)
- [x] 3.5 Подписать `#calendar-swap` на `lesson-saved from:body` с `hx-get` текущей недели (добавить `current_start` в контекст); тест: после `lesson-saved` область календаря обновляется с параметром текущей недели (`tests/test_calendar.py`)
- [x] 3.6 Удалить демо-модалку урока: режим `lesson` в `cal-modal`, `demo_students` из контекста и `saveLesson()` в `calendar.js`; тест: демо-модалка урока и `saveLesson` отсутствуют, слот/отпуск работают (`tests/test_calendar.py`)

## 4. Режимы раскраски

- [x] 4.1 Добавить параметр `?color=target|status` в рендер календаря и серверное окрашивание карточек и точек шапки по активному режиму (цель — цвет `students.color`/`groups.color`, статус — фиксированные синий/красный/серый); тесты: оба режима меняют акцентный цвет карточек (`tests/test_calendar.py`)
- [x] 4.2 Заменить демо-кнопку «Цвет: ученик» на контрол выбора режима («По ученику» / «По статусу»), хранящий выбор в `localStorage` и передающий его в `hx-get` при листании; тест разметки и JS: контрол есть, выбор сохраняется и участвует в запросе (`tests/test_calendar.py`)
- [x] 4.3 Проверить, что цвет карточки и точки в шапке дня совпадают в обоих режимах; тест: точка дня и карточка урока одного акцента (`tests/test_calendar.py`)

## 5. Перенос урока перетаскиванием

- [x] 5.1 Создать `POST /tutor/lessons/{id}/move` (`app/lesson/views/move.py`): принимает `date`/`time`, валидирует владельца (`get_owned_lesson` = 404 для чужого), отклоняет проведённый урок, меняет только `starts_at`, отвечает `HX-Trigger: lesson-saved`; тесты: успешный перенос, чужой урок 404, проведённый отклонён (`tests/test_lesson_update.py`)
- [x] 5.2 Зарегистрировать view в `app/lesson/views/__init__.py` после статических маршрутов; тест: endpoint отвечает и не перехватывает `/students` (`tests/test_lesson_update.py`)
- [x] 5.3 В `calendar.js` при завершении drag с `moved == true` отправлять `htmx.ajax('POST', '/tutor/lessons/{id}/move')` с датой/временем карточки; тест JS: drag завершается сетевым запросом с корректными данными (`tests/test_calendar.py`)
- [x] 5.4 Подавлять `click` после drag (флаг-подавитель + capture-обработчик), чтобы перенос не открывал модалку редактирования; тест: карточка после drag не несёт сработавший `hx-get` (`tests/test_calendar.py`)
- [x] 5.5 Запретить drag для проведённых уроков (`is_completed` → карточка не участвует в жесте); тест: попытка drag проведённого урока не меняет время (`tests/test_calendar.py`)

## 6. Интеграционные проверки

- [x] 6.1 Прогнать полный `uv run pytest` — все тесты зелёные, включая обновлённые `tests/test_calendar.py` (демо-тесты уроков заменены на тесты реальных данных, демо-слоты/отпуск сохранены)
- [x] 6.2 Ручная проверка в браузере: неделя показывает реальные уроки; клик по карточке открывает редактирование; «Добавить» и клик по четверти — создание с префиллом; сохранение обновляет неделю; drag переносит урок на сервер; оба режима раскраски меняют цвета и переживают листание
- [x] 6.3 Проверить `uv run alembic upgrade head` на чистой БД и на БД с существующими учениками/группами — цвета заполнены, дублей внутри одного репетитора нет

## Workflow follow-up

- Зарелектить change (`openspec archive calendar-real-lessons`) после ревью и при зелёных тестах.
- Проверить, что архивация обновила `openspec/specs/calendar`, `lesson-management`, `student-management`, `group-management`.
