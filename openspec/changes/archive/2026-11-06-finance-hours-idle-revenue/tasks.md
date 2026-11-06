# Tasks

## 1. Время и стоимость часа

- [x] 1.1 `app/finance/services/presentation.py`: `duration_label`
  («1 ч 30 мин», «0 мин»), `rate_label` («800 ₽/ч» или «—»),
  `free_hours_phrase` («10,5 свободных часа») и `ratio_label` («2 раза»);
  регистрация в `templates.env.globals`.
- [x] 1.2 `app/finance/services/time_metrics.py`: `rev_per_hour`,
  `time_context` (минуты, подпись, RevPTH) поверх
  `stats.services.hours.completed_minutes`.
- [x] 1.3 `time_metrics.free_minutes`/`idle_window`/`idle_context`: окно
  «сегодня → начало следующего месяца», свободные минуты не ниже нуля,
  сумма потерь и подписи, кнопка в `/tutor/calendar`.

## 2. Типы занятий

- [x] 2.1 `time_metrics.type_split`: выручка одним запросом списаний с JOIN
  по уроку (группа/индивидуальные), минуты по типам, RevPTH каждой колонки;
  сумма колонок равна «Доходу».
- [x] 2.2 `time_metrics.type_insight`: совет о группе при строго высоком
  RevPTH и ненулевых базах, иначе `None`.

## 3. Сводка и семантика «Дохода»

- [x] 3.1 `summary.summary_context(db, tutor, *, start, end)`: начисленный
  доход в `income`, касса в `received`, блоки `time`, `idle`, `types`,
  `type_insight`; docstring модуля переписан.
- [x] 3.2 `views/index.py`, `views/summary.py`: передают объект репетитора.
- [x] 3.3 `analytics.py`/`_analytics.html`: ряд «Доход» → «Получено».

## 4. Шаблон и стили

- [x] 4.1 `finance/_summary.html`: карточка «Доход» — начисление с подписью;
  «Чистый доход» → «Получено от учеников»; «Заработано (уроки)» →
  «Проведено часов»; подпись «Проведено: …» и «Средняя стоимость часа» в
  блоке сравнения.
- [x] 4.2 `_summary.html`: блок «Упущенная выручка» (красная сумма, текст,
  пояснение, кнопка «Посмотреть свободные окна», тихое состояние без суммы)
  и блок «Доходы по типам занятий» с инсайтом.
- [x] 4.3 `styles.css`: `.fin-idle*`, `.fin-types*`, `.fin-compare__sub`,
  `.fin-compare__rate` на токенах темы; адаптив колонок типов (1 → 2 с 640px);
  `static/icons.js` пересобран (`clock`, `hourglass`, `sparkles`).

## 5. Тесты

- [x] 5.1 `tests/test_finance_page.py`: «Доход» = начислено, «Получено от
  учеников» = платежи − возвраты, «Проведено часов», новый список карточек,
  периоды на списаниях.
- [x] 5.2 `tests/test_finance_time.py`: форматтеры, RevPTH, групповой урок
  (часы один раз, выручка вся), разбивка и равенство сумм, инсайт и его
  отсутствие, простой (нулевой рабочий день, нет RevPTH), сценарий бага,
  изоляция по репетитору.
- [x] 5.3 `tests/test_finance_analytics.py`: подпись ряда «Получено».
- [x] 5.4 Полный прогон `uv run pytest -n auto`: 2259 тестов зелёные.

## 6. Документация

- [x] 6.1 Delta-spec `tutor-finance`: новая семантика «Дохода», карточки,
  упущенная выручка, доходы по типам, ряд «Получено».
- [x] 6.2 Основная спека `openspec/specs/tutor-finance/spec.md` обновлена.
- [x] 6.3 `CHANGELOG.md` ([Unreleased]: Добавлено/Изменено/Исправлено) и
  строка «Финансы» в `README.md`.
