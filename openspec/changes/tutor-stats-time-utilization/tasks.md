# Tasks

## 1. Часы и доступность

- [x] 1.1 `app/stats/services/hours.py`: `minutes_to_hours`,
  `completed_minutes`, `planned_minutes`, `student_completed_minutes`,
  `student_regular_minutes`, `week_busy_intervals`. Групповой урок считается
  один раз; пробное входит в фактические часы, но не в регулярные.
- [x] 1.2 `app/stats/services/availability.py`: `workday_minutes`,
  `period_days`, `available_minutes` — рабочий день × дни периода минус
  отметки недоступности; битые границы дают ноль.

## 2. Период, загрузка, карта

- [x] 2.1 `periods.parse_period(params, tutor, *, default="all")`:
  «Обзор» вызывает с `default="30d"`, «Новые и пробные» — без изменений.
- [x] 2.2 `app/stats/services/utilization.py`: проценты «факт к цели» и «факт к
  максимуму», тона (<70 / 70–90 / >90), масштабирование недельной цели на
  период, флаг «цель не задана», подсказка.
- [x] 2.3 `app/stats/services/heatmap.py`: сетка Пн–Вс × часы рабочего дня,
  состояния занято/свободно/недоступно, инсайт о самом большом окне.

## 3. Отображение

- [x] 3.1 `presentation.py`: `hours_label`, `hours_phrase`, `percent_or_dash`;
  регистрация в `templates.env.globals`.

## 4. Обзор, ученики, CSV

- [x] 4.1 `overview.py`: выручка за период, «Выручка на час» вместо LTV,
  контекст загрузки и карты, часы в прогнозе, список падения нагрузки и
  счётчик риска.
- [x] 4.2 `student_rows.py`: `hours_week`, окна 2×14 дней, флаг `decline` и
  процент падения; `SORT_OPTIONS`, `sort_rows`, `sort` в `apply_filters`.
- [x] 4.3 `csv_export.py`: колонка «Часов/нед».
- [x] 4.4 `views/index.py`: период на «Обзоре», `sort` в «Учениках»;
  `views/students_csv.py`: `sort` в выгрузке.

## 5. Шаблоны и стили

- [x] 5.1 `stats/_period.html` — общий партиал периода; подключён в
  `_new.html` и `_overview.html`.
- [x] 5.2 `_overview.html`: блок «Загрузка», часы под прогнозом, «Выручка на
  час», «Карта загрузки», флаг падения нагрузки в «Риске потери».
- [x] 5.3 `_students.html`: колонка «Часов/нед», выбор сортировки, подсказка.
- [x] 5.4 `styles.css`: `.stats-util*`, `.stats-heat*`, `.stats-flag`,
  `.stats-risk__subhead`, `.stats-kpi__sub--hours` — на существующих токенах.

## 6. Тесты

- [x] 6.1 `tests/test_stats.py`: «Выручка на час» вместо LTV, часы в прогнозе.
- [x] 6.2 `tests/test_stats_hours.py`: групповой урок, пробное, доступные часы
  с отпуском и выходным, битые границы, пороги, карта и инсайт, «Выручка на
  час», колонка и сортировка по часам, флаг −62% и отрицательные случаи,
  период 30 дней по умолчанию.
- [x] 6.3 Полный прогон: `uv run pytest -n auto` (2242 теста) и
  `ruff check --select E9,F63,F7,F82`.

## 7. Документация

- [x] 7.1 Delta-spec `stats`: загрузка, карта загрузки, флаг падения нагрузки,
  изменения «Обзора» и таблицы учеников.
- [x] 7.2 `CHANGELOG.md`: строка в `[Unreleased] → Добавлено`.