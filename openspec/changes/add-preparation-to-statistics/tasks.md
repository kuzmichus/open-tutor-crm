# Tasks

## 1. Сервис расчёта

- [x] 1.1 `app/stats/services/preparation.py`: константы
  `BURNOUT_WEEKLY_HOURS = 40`, `WEEK_DAYS = 7`, геометрия пончика.
- [x] 1.2 `preparation_context(db, tutor, *, actual_minutes, days)`: коэффициент
  из `get_settings`, подготовка = минуты × коэффициент, общая занятость,
  недельные значения, инсайт, алерт, легенда и `chart`.
- [x] 1.3 Крайние случаи: коэффициент 0, отсутствие уроков, битое/NULL значение
  коэффициента, `days <= 0`.

## 2. Контекст «Обзора»

- [x] 2.1 `app/stats/services/overview.py`: посчитать `days` один раз, передать
  в `utilization_context(..., days=days)` и добавить
  `preparation=preparation_context(...)`.
- [x] 2.2 `app/stats/services/utilization.py`: необязательный параметр `days`
  (без него считается как раньше).

## 3. Шаблон и стили

- [x] 3.1 `app/stats/templates/stats/_overview.html`: инсайт в блоке
  «Загрузка» после полос.
- [x] 3.2 `_overview.html`: карточка «Баланс времени (Уроки vs Подготовка)» с
  SVG-пончиком, легендой, пояснением коэффициента и пустым состоянием.
- [x] 3.3 `_overview.html`: алерт выгорания только при
  `overview.preparation.alert`.
- [x] 3.4 `app/static/styles.css`: `.stats-util__insight`, `.stats-balance*`,
  `.stats-burnout*` — на существующих токенах, без литералов цвета.

## 4. Тесты

- [x] 4.1 `tests/test_stats_preparation.py`: дефолт 0.7, сохранённый
  коэффициент, недельный пересчёт, коэффициент 0, отсутствие уроков, порог
  40/40.1, геометрия пончика, легенда.
- [x] 4.2 Интеграционные тесты страницы: инсайт, виджет, пустое состояние,
  алерт выше и ниже порога, смена коэффициента меняет числа.
- [x] 4.3 Полный прогон `uv run pytest -q` и `ruff check`.

## 5. Документация

- [x] 5.1 `CHANGELOG.md`: строка в `[Unreleased] → Добавлено`.
- [x] 5.2 `README.md`: дополнить описание «Статистики».
- [x] 5.3 `openspec validate add-preparation-to-statistics --strict`.
- [x] 5.4 Основная спека `openspec/specs/stats/spec.md` синхронизируется при
  архивировании изменения (ADDED-требования нельзя дублировать заранее).