# Tasks

## 1. Расчёт

- [x] 1.1 `app/stats/services/preparation.py`: сделать публичными
  `coefficient_label(value)` и `preparation_minutes(actual_minutes, coefficient)`;
  `preparation_context` вызывает их же — поведение «Статистики» не меняется.
- [x] 1.2 `app/finance/services/time_metrics.py`: в `time_context` получить
  коэффициент из `get_settings`, посчитать часы подготовки и общую занятость,
  добавить в контекст `coefficient`, `coefficient_label`, `preparation_minutes`,
  `preparation_label`, `has_preparation`, `total_minutes`, `total_label`,
  `real_rev_per_hour`, `real_rev_per_hour_label`, `real_insight`.
- [x] 1.3 `time_metrics.py`: `real_rate_insight(*, nominal, real, coefficient)` —
  `None` без подготовки/ставки, иначе совет с ценой
  `номинал × (1 + коэффициент)`.
- [x] 1.4 Docstring модуля и `summary.py`: подготовка считается по проведённым
  урокам, база и формула совпадают со «Статистикой».
- [x] 1.5 `time_metrics.idle_context`: цена простоя считается по реальной
  ставке (`real_rev`, `coefficient`), в контексте — `real_rate_label` и
  `has_preparation`; `summary.py` передаёт ставку и коэффициент из
  `time_context`.

## 2. Шаблон и стили

- [x] 2.1 `finance/_summary.html`, карточка «Проведено часов»: мелкая строка
  «+ Y на подготовку» при `has_preparation`.
- [x] 2.2 `_summary.html`, блок «Заработано и получено»: та же строка под
  «Проведено: …».
- [x] 2.3 `_summary.html`: «Реальная стоимость часа» рядом со «Средней
  стоимостью часа», подсказка о коэффициенте со ссылкой на профиль и
  плашка-совет `fin-compare__insight`.
- [x] 2.4 `app/static/styles.css`: правило `.fin-compare__insight` на
  существующих токенах (`--warning-soft`, `--warning-fg`).

## 3. Тексты о коэффициенте

- [x] 3.1 `app/tutor/models/tutor_settings.py`: комментарий — коэффициент
  используется в «Статистике» и «Финансах».
- [x] 3.2 `app/tutor/templates/tutor/_tab_calendar.html`: подсказка поля
  называет страницы, где значение применяется.

## 4. Тесты

- [x] 4.1 `tests/test_finance_preparation.py`: `preparation_minutes`,
  `coefficient_label`, `real_rate_insight` (включая `None`-случаи).
- [x] 4.2 HTTP-сценарии: коэффициент по умолчанию, сохранённый 1.2, нулевой,
  отсутствие проведённых уроков.
- [x] 4.3 Изоляция репетиторов и совместимость с блоком НПД.
- [x] 4.4 Прогон `tests/test_finance_preparation.py`, `test_finance_time.py`,
  `test_finance_page.py`, `test_finance_npd.py`, `test_css_styles.py`,
  `test_stats_preparation.py`, `test_profile.py` и полного набора.
- [x] 4.5 `test_idle_profit_uses_real_rate` и
  `test_idle_profit_zero_coefficient_uses_nominal_rate`: сумма простоя
  считается по реальной ставке, подпись упоминает подготовку только при
  ненулевом коэффициенте; тесты `test_finance_time.py` обновлены под новое
  название блока.

## 5. Документация

- [x] 5.1 `openspec/specs/tutor-finance/spec.md` и
  `openspec/specs/tutor-profile-settings/spec.md` — синхронизированы с
  требованиями изменения.
- [x] 5.2 `CHANGELOG.md`: расширен пункт про коэффициент и добавлена строка про
  часы подготовки и реальную стоимость часа.
- [x] 5.3 `README.md`: описание «Финансов» дополнено.
- [x] 5.4 `openspec validate finance-preparation-hours --strict`.
