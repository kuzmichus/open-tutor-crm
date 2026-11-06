# Tasks

## 1. Сервис расчёта

- [x] 1.1 `app/stats/services/workload.py`: пороги уровней недельной
  нагрузки `COMFORT_WEEKLY_HOURS = 35`, `HIGH_WEEKLY_HOURS = 45`,
  `WEEK_DAYS = 7`, `level()`, `verdict()`, `weekly_minutes()`.
- [x] 1.2 `app/stats/services/preparation.py`: геометрия пончика,
  `preparation_context(db, tutor, *, actual_minutes, days)`: коэффициент
  из `get_settings`, подготовка = минуты × коэффициент, общая занятость,
  недельные значения, инсайт с вердиктом, алерт, легенда и `chart`.
- [x] 1.3 Крайние случаи: коэффициент 0, отсутствие уроков, битое/NULL значение
  коэффициента, `days <= 0`.

## 2. Контекст «Обзора»

- [x] 2.1 `app/stats/services/overview.py`: посчитать `days` один раз,
  посчитать `preparation_context` до загрузки, передать в
  `utilization_context(..., preparation_minutes=..., days=days)` и положить
  `preparation` в контекст.
- [x] 2.2 `app/stats/services/utilization.py`: необязательные параметры
  `days` и `preparation_minutes` (без них поведение прежнее).
- [x] 2.3 `app/stats/services/utilization.py`: вторая шкала — «Загрузка
  ресурса» (`resource_hours`, `resource_percent`, `resource_bar`), тон по
  абсолютным недельным часам (`resource_tone`), «Факт к цели» — по проценту
  с порогами 70 и 100.

## 3. Шаблон и стили

- [x] 3.1 `app/stats/templates/stats/_overview.html`: инсайт в блоке
  «Загрузка» после полос, тон подписи по уровню нагрузки.
- [x] 3.2 `_overview.html`: вторая шкала «Загрузка ресурса» с подписью
  «общая занятость из доступных часов» и обновлённой подсказкой блока.
- [x] 3.3 `_overview.html`: карточка «Баланс времени (Уроки vs Подготовка)» с
  SVG-пончиком, легендой, пояснением коэффициента и пустым состоянием.
- [x] 3.4 `_overview.html`: алерт выгорания только при
  `overview.preparation.alert`.
- [x] 3.5 `app/static/styles.css`: `.stats-util__insight` с тонами
  `--comfort/--high/--burnout`, `.stats-util__bar--ok/--warn/--danger`,
  `.stats-balance*`, `.stats-burnout*` — на существующих токенах, без
  литералов цвета.

## 4. Тесты

- [x] 4.1 `tests/test_stats_preparation.py`: дефолт 0.7, сохранённый
  коэффициент, недельный пересчёт, коэффициент 0, отсутствие уроков, порог
  45/45.1, уровни нагрузки 35/45, вердикт инсайта, геометрия пончика, легенда.
- [x] 4.2 Интеграционные тесты страницы: инсайт, виджет, пустое состояние,
  алерт выше и ниже порога, смена коэффициента меняет числа.
- [x] 4.3 Тесты «Загрузки ресурса»: общая занятость против календаря, зелёная
  шкала при 81% полосы, жёлтая при 35–45 ч, красная при >45 ч.
- [x] 4.4 `tests/test_stats_hours.py`: новые пороги «Факта к цели» (70/100),
  цвет второй шкалы по часам, отсутствие «Факта к максимуму».
- [x] 4.5 Полный прогон `uv run pytest -q` и `ruff check`.

## 5. Документация

- [x] 5.1 `CHANGELOG.md`: строка в `[Unreleased] → Добавлено`.
- [x] 5.2 `README.md`: дополнить описание «Статистики».
- [x] 5.3 `openspec validate add-preparation-to-statistics --strict`.
- [x] 5.4 Основная спека `openspec/specs/stats/spec.md` синхронизируется при
  архивировании изменения (ADDED-требования нельзя дублировать заранее).