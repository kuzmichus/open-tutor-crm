# Tasks

## 1. Данные и сервисы

- [x] 1.1 Модель `StudentAccess` (`app/student/models/student_access.py`): UNIQUE
      `student_id`, UNIQUE `login`, CHECK длины логина; регистрация в `app/models.py`;
      миграция autogenerate.
- [x] 1.2 Сервис `credentials.py`: валидация логина/пароля, `generate_password`,
      `save_access` (создание и смена пароля), ошибка занятого логина.
- [x] 1.3 Сервис `list_metrics.py`: агрегаты карточек (баланс, проведено, следующий
      урок, первая оплата, последняя цена, «осталось»), сводка долга.
- [x] 1.4 Сервис `student_lessons.py`: уроки ученика (индивидуальные + групповые),
      фильтр статуса, сортировка newest-first.
- [x] 1.5 Сервис `report.py`: окно месяца в зоне педагога, стат-карточки отчёта.
- [x] 1.6 `students.py`: сортировка `sort=lastname|firstname`; `presentation.py`:
      `next_lesson_label`, `short_date_label`, `month_label`.

## 2. Views

- [x] 2.1 `index.py` + `list_partial.py`: параметры `sort`, `debtors`; долг в контексте.
- [x] 2.2 `lessons_modal.py`: GET `/tutor/students/{id}/lessons`.
- [x] 2.3 `report_modal.py`: GET `/tutor/students/{id}/report`.
- [x] 2.4 `access_form.py` (GET) и `access_save.py` (POST) `/tutor/students/{id}/access`.
- [x] 2.5 Сборка роутеров; статические маршруты раньше `/{student_id}`.

## 3. Шаблоны и стили

- [x] 3.1 `index.html`: шапка (Назад, Импорт), тулбар (переключатель вида, сортировка,
      «Удалённые», поиск), контейнер `#students-content`, `#modal-lesson`.
- [x] 3.2 `_list.html`: панель долга + сетка карточек + таблица; `_card.html`: метрики,
      следующий урок, кнопки «Уроки/Отчёт/Доступ/Редактировать».
- [x] 3.3 Модалки `_lessons_modal.html`, `_report_modal.html`, `_access_modal.html`,
      `_access_saved.html`.
- [x] 3.4 `styles.css`: блоки `students-debt`, `student-stats`, `student-lessons`,
      `report-*`, `access-*`; только токены, плоский BEM.
- [x] 3.5 `students.js`: `toggleDeleted`, фабрика `studentAccess` (генерация пароля).

## 4. Тесты и документация

- [x] 4.1 Обновить `test_students_ui.py` (карточка с метриками, таблица, панель долга)
      и `test_students_pages.py` (колонки таблицы).
- [x] 4.2 `test_students_metrics.py`: агрегаты, долг, фильтр должников, сортировка.
- [x] 4.3 `test_students_access.py`: валидация, уникальность логина, показ данных один
      раз, смена пароля, изоляция 404, вход без сессии.
- [x] 4.4 Модалки уроков и отчёта: фильтры, месяц, изоляция, рубль.
- [x] 4.5 README и спека `student-management` (delta).
