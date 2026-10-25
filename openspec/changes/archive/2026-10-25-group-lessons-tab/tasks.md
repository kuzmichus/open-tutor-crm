# Tasks

## 1. Сервис выборки (`lesson`)

- [x] 1.1 Написать `app/lesson/services/group_lessons.py`: `normalize_status` (закрытый список из `LESSON_STATUSES`, неизвестное — «Все») и `list_group_lessons` (один `SELECT` с `LEFT JOIN homework`, порядок `starts_at` по убыванию, фильтр по статусу); проверить юнит-тестом нормализацию
- [x] 1.2 Добавить в `app/lesson/services/presentation.py` `format_lesson_date` («17.05.2027») и `homework_short_label` («ДЗ: есть/нет», «Не задано» = «нет») и зарегистрировать в общем Jinja-окружении

## 2. Маршрут, панель и второй слой

- [x] 2.1 Ри-экспортировать `get_owned_group` в `app/lesson/services/access.py`; создать `app/lesson/views/group_lessons.py` (`GET /tutor/groups/{group_id}/lessons`, параметр `status`) и подключить роутер в `app/lesson/views/__init__.py`; проверить тестами изоляции: чужая группа — 404, без сессии — 303 на логин
- [x] 2.2 Написать `app/lesson/templates/lesson/_group_panel.html` с корнем `#group-lessons-content`: чипы статуса (`.period-chips`, `hx-get` на маршрут, `hx-target` — корень), строки-карточки занятий с `hx-target="#modal-lesson"`, пустые состояния («У группы пока нет занятий.», «Нет занятий с таким статусом.»)
- [x] 2.3 Заменить заглушку вкладки «Занятия» в `app/group/templates/group/_manage.html` на слот с `hx-trigger="load, lesson-saved from:body, homework-saved from:body"` и `hx-swap="outerHTML"` на маршрут панели
- [x] 2.4 Добавить на страницу групп (`app/group/templates/group/index.html`) контейнер `#modal-lesson` и скрипт `lessons.js`; добавить блок `group-lessons` в `app/static/styles.css` (список, строки-кнопки, мета-строка с иконками); проверить `tests/test_css_styles.py`
- [x] 2.5 Параметризовать слой модалки урока: `modal_target` в `lesson_form_context` (по умолчанию `#modal`), `hx-target` в `_form.html` — из контекста, `_modal_target(request)` в `app/lesson/views/update.py` по заголовку `HX-Target`
- [x] 2.6 Добавить `HX-Trigger: homework-saved` на успех сохранения ДЗ (`app/homework/views/save.py`)

## 3. Тесты и спека

- [x] 3.1 Написать `tests/test_group_lessons.py`: список «новые сверху», кликабельные строки во второй слой, индикатор ДЗ (есть/нет/не задано), фильтры статуса и неизвестное значение, пустые состояния, изоляция 404, без сессии — 303; `HX-Target: modal-lesson` на GET и на POST с ошибкой валидации; удаление — пустой ответ с `lesson-saved`; страница групп несёт `#modal-lesson` и `lessons.js`
- [x] 3.2 Обновить `tests/test_group_manage.py`: параметризация заглушек — только «Расписание»; вкладка «Занятия» содержит слот панели и не содержит текста заглушки
- [x] 3.3 Обновить `tests/test_homework.py`: успех сохранения ДЗ шлёт `HX-Trigger: homework-saved`
- [x] 3.4 Обновить `openspec/specs/group-management/spec.md`: сузить требование заглушек до вкладки «Расписание», добавить требование «Вкладка «Занятия» группы» (сценарии: открытие, фильтр, открытие занятия во втором слое, изоляция); README — раздел про вкладку «Занятия» группы
