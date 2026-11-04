# Tasks

## 1. Палитра Google и выбор цвета

- [x] 1.1 `app/gcalendar/services/event_color.py`: `GOOGLE_EVENT_COLORS`
  (11 цветов событий Calendar API v3), `PALETTE_COLOR_IDS` (16 цветов
  `app/common/colors.PALETTE` + `DEFAULT_TARGET_COLOR` → `colorId`),
  `DEFAULT_COLOR_ID`. Проверка:
  `uv run pytest tests/test_gcalendar_event_color.py`.
- [x] 1.2 `color_id(color: str | None) -> str`: нормализация hex (регистр,
  пробелы, `#`), точное совпадение по таблице, иначе ближайший цвет по
  расстоянию в CIELAB; `None`/пустое/некорректное → `DEFAULT_COLOR_ID`.
  Проверка: тесты на все 17 значений, регистр, мусор и `None`.
- [x] 1.3 Проверить таблицу расчётом: каждый hex палитры и default дают
  ожидаемый `colorId`; спорные случаи (`#8c3cdd` → Grape, `#c83cdd` →
  Grape) закреплены таблицей, а не метрикой.

## 2. Тело события и синхронизация

- [x] 2.1 `app/gcalendar/services/event_payload.py`: `build_event` получает
  `target_color: str | None = None` и кладёт `payload["colorId"] =
  event_color.color_id(target_color)`.
- [x] 2.2 Там же: `"colorId"` добавлен в `_HASH_FIELDS` — смена цвета даёт
  PATCH, неизменный цвет не даёт запросов.
- [x] 2.3 `app/gcalendar/services/sync.py::build_payload`: передать
  `target_color=group.color` для группового урока и `student.color` для
  остальных (объекты уже загружены — новых запросов к БД нет).
- [x] 2.4 Проверить, что `build_event` вызывается только из
  `sync.build_payload`, а `api.list_event_ids` читает лишь `items(id)` —
  правок в транспорте не требуется.

## 3. Тесты

- [x] 3.1 Новый `tests/test_gcalendar_event_color.py`: 11 цветов Google,
  полнота таблицы, все 17 соответствий, регистр и пробелы, `None`/пустое/
  мусор → default, ближайший цвет для незнакомого hex, тип результата.
- [x] 3.2 `tests/test_gcalendar_sync.py::test_sync_creates_event_with_local_time`:
  ученик с цветом `#dd3c3c` → в теле `colorId == "11"`.
- [x] 3.3 `tests/test_gcalendar_sync.py`: смена цвета ученика даёт PATCH,
  `content_hash` меняется, `event_id` сохраняется; групповой урок берёт цвет
  группы; цель без цвета получает default; без смены цвета запросов нет.
- [x] 3.4 `tests/test_gcalendar_reconcile.py`: сверка PATCH-ит событие после
  смены цвета цели и окрашивает событие, созданное до раскраски (хеш без
  `colorId`) — бэкфилл без миграции.

## 4. Регресс и документация

- [x] 4.1 `uv run pytest -n auto` — весь набор зелёный (2071 тест).
- [x] 4.2 Линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py` — без ошибок.
- [x] 4.3 `openspec validate add-google-calendar-event-colors --strict` — валиден.
- [x] 4.4 `README.md`, раздел «Как подключить Google Календарь»: событие
  окрашивается в ближайший к цвету ученика или группы цвет, палитра Google
  уже — оттенок может отличаться.
- [x] 4.5 `CHANGELOG.md`, `[Unreleased]` → «Добавлено»: цвет событий по цвету
  ученика или группы.

## Workflow follow-up

- Архив change'а — после ревью (`openspec archive add-google-calendar-event-colors`).
