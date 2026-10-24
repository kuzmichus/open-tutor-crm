# Tasks

## 1. Модель и миграция

- [x] 1.1 Создать `app/unavailability/` (`__init__.py`, `models/`, `services/`, `views/`, `templates/unavailability/`) и убедиться, что структура повторяет доменный модуль из AGENTS.md
- [x] 1.2 Написать модель `TutorUnavailability` в `app/unavailability/models/unavailability.py` с кортежами `UNAVAILABILITY_MODES`, `PERIOD_REASONS`, `DAYOFF_REASON`, `REASON_LABELS`, `WEEKDAY_LABELS` и двумя CHECK-ограничениями `ck_unavailability_period` / `ck_unavailability_weekday`; проверить тестом `tests/test_unavailability_models.py`, что БД отклоняет период без `start_date`, выходной без `weekday` и причину вне списка
- [x] 1.3 Зарегистрировать модель в `app/models.py` (`from app.unavailability.models.unavailability import TutorUnavailability  # noqa: F401`) и проверить, что таблица есть в `Base.metadata.tables`
- [x] 1.4 Создать миграцию `uv run alembic revision --autogenerate -m "add tutor unavailability"`, проверить наличие FK `ondelete=CASCADE` и CHECK в сгенерированном файле, применить `uv run alembic upgrade head` и убедиться, что `uv run alembic heads` совпадает с новой ревизией

## 2. Сервисы недоступности

- [x] 2.1 Реализовать `app/unavailability/services/access.py` с `get_owned_unavailability` (id и tutor_id одним `SELECT`, чужое = 404) и ри-экспортом `require_tutor_id`; проверить тестом изоляции: чужой репетитор получает 404, а не 403
- [x] 2.2 Реализовать `app/unavailability/services/marks.py`: `marks_for_week(db, tutor_id, monday)` одним запросом с `OR` двух форм и `coverage_for_week(db, tutor_id, monday)` → `dict[date, DayMark]` с приоритетом `period` над `weekday`; проверить юнит-тестами покрытие периода с `end_date=NULL`, покрытие выходного с `until_date=NULL` и приоритет двух отметок на одном дне
- [x] 2.3 Реализовать `app/unavailability/services/unavailability_form.py`: разбор формы режима «Период» (причина из закрытого списка, первый день обязателен, последний не раньше первого, пустой последний = бессрочно) и режима «Постоянный выходной» (день недели 0–6, причина всегда «Выходной»); проверить тестами ошибок: причина вне списка, конец раньше начала, отсутствие дня недели
- [x] 2.4 Реализовать `app/unavailability/services/unavailability_writer.py` (создание, изменение срока, удаление) и `presentation.py` (подписи причин, формат срока «26.10 – 30.10», «с 26.10 — бессрочно», «сб, бессрочно»); проверить юнит-тестами форматов срока и смену `end_date`/`until_date` без изменения причины и первого дня
- [x] 2.5 Реализовать `app/unavailability/services/warning.py` с `unavailability_warning(db, tutor_id, occurrences)` → `(reason_label, count) | None`: пересечение списка дат начала занятий с покрытием; проверить тестом, что число совпадает с числом дат, попавших в отмеченные дни

## 3. Панель «Отпуск и выходные»

- [x] 3.1 Реализовать вьюхи `panel.py` (GET `/tutor/unavailability`), `create.py`, `update_end.py` (`POST /{id}/end`), `delete.py` (`POST /{id}/delete`), собрать роутер в `views/__init__.py` (статические маршруты до `/{id}`) и подключить в `main.py`; проверить тестом, что панель открывается с сессией и редиректит без неё
- [x] 3.2 Написать шаблон `templates/unavailability/_panel.html`: переключатель режима, форма новой отметки, блок «Уже отмечено» с кнопками «Изменить срок» и «Снять», свёрнутый блок «Показать прошедшие»; форма — `hx-target` на саму себя, `hx-swap="outerHTML"`, успех возвращает панель с `HX-Trigger: unavailability-saved`; проверить тестом разметку (поля обоих режимов, обе кнопки, пустое состояние списка)
- [x] 3.3 Добавить `app/unavailability/templates` в `TEMPLATE_DIRS` (`app/templating.py`) и хелперы отображения через `register_template_helpers()`; проверить, что подписи причин доступны в шаблоне без импорта вьюх
- [x] 3.4 Описать в `app/static/styles.css` все литеральные BEM-классы панели и прогнать `uv run pytest -q tests/test_css_styles.py`, добавив панель в параметризацию проверки классов
- [x] 3.5 Проверить тестами поведение панели через HTTP: создание отметки периода и выходного, ошибка «конец раньше начала» с возвратом присланных значений, «Изменить срок» меняет только срок, «Снять» удаляет отметку, после каждого действия панель возвращается с обновлённым списком

## 4. Календарь: рендер отмеченных дней

- [x] 4.1 Заменить в `app/calendar/services/week_days.py` демо-отпуск на `coverage_for_week` и вернуть дни с отметкой в контексте; проверить тестом, что неделя с отметкой отдаёт причину дня, а неделя без отметок — пустой `unavailable`
- [x] 4.2 Дополнить `build_day_view` в `app/calendar/services/presentation.py` полями `unavailable` (подпись причины) и `unavailable_title` (все причины для подсказки), убрать `has_vacation`; пересчитать `is_empty` как «нет уроков и нет отметок»; проверить тестами приоритет причины и текст пустой недели с отметкой
- [x] 4.3 Обновить `app/calendar/templates/calendar/_area.html`: причина в шапке дня вместо «Выходной» и счётчика занятий, штриховка тела дня, `data-unavailable` у `.cal-day`, удалить блок `.cal-vacation`; проверить тестом разметку дня с отметкой и отсутствие `.cal-vacation`
- [x] 4.4 Добавить в `app/static/styles.css` токен `--cal-off` и правило штриховки недоступности, визуально отличное от `.cal-day--weekend`; проверить тестом CSS, что оба класса имеют собственные правила и что `.cal-vacation` больше не описан
- [x] 4.5 Переименовать пункт меню «Добавить отпуск» в «Отпуск и выходные» и направить его на панель (`hx-get` в `#modal`); проверить тестом, что пункт есть в меню и не открывает форму урока

## 5. Предупреждения при постановке урока

- [x] 5.1 В `app/lesson/views/create.py` добавить проверку `unavailability_warning` до записи: без `ack_unavailable` форма возвращается с баннером и присланными значениями, с флагом — урок или серия создаются; проверить тестами «без подтверждения урок не создан», «с подтверждением создан», «серия: одно предупреждение с числом затронутых»
- [x] 5.2 Добавить в `lesson_form_context` ключ `unavailable_warning` и вывести баннер в `app/lesson/templates/lesson/_form.html` рядом с существующим `form-hint--warning`, отдельно от `errors`, со скрытым полем `ack_unavailable`; проверить тестом разметку баннера и отсутствие его в блоке ошибок
- [x] 5.3 Провести `ack_unavailable` через `parse_lesson_form` и `lesson_writer` (не как поле урока, а как признак подтверждения) и убедиться тестом, что повторная отправка без флага снова показывает предупреждение
- [x] 5.4 В `app/lesson/views/update.py` предупреждать при смене начала на отмеченный день; проверить тестом: урок не изменён без подтверждения, изменено только начало с подтверждением
- [x] 5.5 В `app/lesson/views/move.py` отклонять перенос в отмеченный день без `ack_unavailable`, возвращая предупреждение с причиной; проверить тестами перенос без флага (время прежнее) и с флагом (время сохранено)
- [x] 5.6 В `app/static/calendar.js` заменить guard `.cal-vacation` в `openSlot` на чтение `data-unavailable` с `confirm()`, добавить `confirm()` в `onDragEnd` до `appendChild` (при отказе карточка остаётся на месте) и передавать `ack_unavailable=1` в `openLessonForm` и `moveLesson`; проверить статическими тестами наличие обеих проверок и отсутствие `vacationForm`

## 6. Удаление демо-слоя

- [x] 6.1 Перенести `week_start()` в `app/calendar/services/week.py` и `lessons_word()` в `app/calendar/services/presentation.py`, обновить импорты в `views/index.py`, `presentation.py` и тестах; прогнать `uv run pytest -q tests/test_calendar.py`
- [x] 6.2 Удалить `demo_schedule.py` и его тесты (`test_demo_*`), удалить `kind`, `VACATION`, `is_lesson` из `schedule_event.py` и заменить `ScheduleDay.lessons` на `events`; убедиться, что `grep -rn "demo_schedule\|VACATION" app tests` не находит совпадений
- [x] 6.3 Удалить из `app/static/calendar.js` `vacationForm`, `openVacationDialog`, `closeVacation`, `createVacation` и из `_area.html` диалог `#cal-vacation-form`; удалить тесты DOM-отпуска (`test_calendar_vacation_*`, `test_calendar_keeps_demo_vacation_with_real_lessons`) и проверить, что `grep -n "vacation" app/static/calendar.js app/calendar/templates/calendar/_area.html` пуст
- [x] 6.4 Прогнать полный `uv run pytest` и убедиться, что удаление демо не сломало тесты уроков, слотов и раскраски

## 7. Документация и приёмка

- [x] 7.1 Обновить `README.md`: убрать «календарь пока наполняется демо-данными», добавить недоступность в список возможностей и снять чекбокс про отпуска из плана
- [x] 7.2 Пройти сценарий вручную в браузере: создать отпуск на период, увидеть штриховку и причину в шапке, перелистнуть недели и вернуться, продлить срок, поставить урок в отмеченный день с подтверждением, создать серию с предупреждением о числе занятий, снять отметку — и записать результат в описании задачи

  **Результат:** пройдено в headless-Chromium (Playwright), 25/25 проверок PASS.
  Сценарий: регистрация → вход → календарь 26.10–01.11.2026 → меню «⋯» →
  пункт «Отпуск и выходные» (форма урока не открылась) → панель → отпуск
  26.10–30.10 → 5 дней заштрихованы, в шапке «Отпуск», `data-unavailable="Отпуск"`
  → листание вперёд (01.11–08.11: 0 отмеченных дней) и назад (снова 5) →
  «Изменить срок» на 06.11 (строка стала «26.10 – 06.11», отметка не
  размножилась) → клик по четверти 27.10 10:00: `confirm()` с причиной,
  форма открылась с префиллом и скрытым `ack_unavailable=1` → урок создан и
  виден в отмеченном дне → серия: баннер «Дни отмечены как недоступные:
  Отпуск. Затронуто занятий: 2. Всё равно поставить уроки?» → «Снять» →
  «Точно снять?» → список пуст, штриховка из календаря исчезла.

  **Найдено и исправлено в ходе прогона:** кнопка «Успешно сохранено» в панели
  оставалась неактивной навсегда — повторно добавить отметку было нельзя.
  Добавлен сброс через `data-un-save` + `restoreUnavailabilityButton`
  (паттерн кнопки «Сохранить ДЗ») и тест
  `test_panel_success_button_is_restored_after_save`.

  Артефакты: `/tmp/opencode/test-result/unavailability-manual/`
  (`summary.md`, 16 скриншотов).
- [x] 7.3 Проверить `openspec validate add-tutor-unavailability` и убедиться, что дельта `vacation-creation` снимает все требования (архив удалит спеку)

## Workflow follow-up

- Архивировать change после ревью и проверки требований проекта (`/opsx-archive`), убедившись, что `openspec/specs/vacation-creation/` исчезла, а `tutor-unavailability` появилась.

## Follow-up после ревью: выходные задаёт только таблица

Правка по замечанию ревью: в проекте единственный источник выходных — записи в `tutor_unavailability`, поэтому автоматическое выделение сб/вс по номеру дня недели удалено.

- [x] Убрать флаг `is_weekend` из `ScheduleDay` и `build_week_days` (сб/вс больше не отличаются от будней)
- [x] Убрать из `_area.html` плашку «Выходной» и классы `cal-dayhead--weekend` / `cal-day--weekend`
- [x] Удалить из `styles.css` правила `.cal-day--weekend`, `.cal-dayhead--weekend` и токены `--cal-weekend` / `--cal-hatch`; штриховка осталась только у `.cal-day--unavailable`
- [x] Обновить тесты: `test_calendar_weekend_has_no_badge`, `test_calendar_weekend_has_no_hatching`, `test_weekend_rules_are_removed_from_css`; переписаны тесты, опиравшиеся на класс шапки выходного (добавлен хелпер `_dayhead`)
- [x] Спека `calendar` в дельте: требование «Выходные визуально отделены» перенесено в REMOVED, в «Шапке дней недели» сформулирован запрет автоматического выделения сб/вс
- [x] `design.md` D4: зафиксировано, что единственный источник выходных — отметки, и что предупреждение в форме урока срабатывает только на отметки
- [x] `uv run pytest` — 805 passed; `openspec validate add-tutor-unavailability` — valid
