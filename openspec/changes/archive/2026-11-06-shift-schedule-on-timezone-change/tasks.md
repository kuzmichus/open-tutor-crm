# Tasks

## 1. Сервис пересчёта моментов времени

- [x] 1.1 `app/tutor/services/timezone_shift.py`: `shift_moment(value,
  old_zone, new_zone)` — `as_utc` → старая зона → настенное время
  (`replace(tzinfo=None)`) → новая зона → UTC; per-row DST, `fold=0`.
- [x] 1.2 Там же `tutor_lessons(db, tutor_id)` — все уроки репетитора
  (прошедшие и будущие, любой статус) через JOIN `students`/`groups`.
- [x] 1.3 Там же `shift_tutor_schedule(db, tutor_id, old_zone, new_zone)`
  без коммита: уроки → окна (двухфазно, обход `uq_slots_tutor_start`) →
  сроки ДЗ (`due_at IS NOT NULL`) → `occurred_at` списаний по новому
  `lesson.starts_at`. Возвращает счётчики.
- [x] 1.4 Проверка: `tests/test_timezone_shift.py` — юнит `shift_moment`
  (вперёд, назад, naive-вход, DST по строкам, old == new), сервис
  (счётчики, настенное время, изоляция, коллизия окон, `due_at = NULL`).

## 2. Сохранение вкладки «Календарь»

- [x] 2.1 `app/tutor/views/profile_calendar.py`: имя зоны из формы →
  сравнение с `tutor_zone_name(tutor)`; при изменении —
  `shift_tutor_schedule` до записи `tutor.timezone`; затем `save_settings`
  коммитит сдвиг и настройки одной транзакцией.
- [x] 2.2 Там же: после коммита — best-effort `resync_tutor_events` в
  `try/except Exception` с логом.
- [x] 2.3 Проверка: `tests/test_timezone_shift.py` — POST со сменой зоны
  сдвигает урок и ДЗ, сохраняет настенное время; сохранение той же зоны
  ничего не меняет; критерий приёмки — карточки календаря до и после
  смены зоны совпадают, бейдж `.cal-tz` показывает новую зону.

## 3. События Google Календаря

- [x] 3.1 `app/gcalendar/services/sync.py::resync_tutor_events(db, tutor)` —
  обход `mapping.event_ids_of_tutor`, `sync_lesson` по каждому уроку,
  счётчики `(обновлено, без изменений, ошибок)`; без подключения — нули.
- [x] 3.2 Проверка: `tests/test_gcalendar_sync.py` — PATCH с новой зоной
  и прежним настенным временем; PATCH прошедшего урока; при
  `GOOGLE_CALENDAR_SYNC=false` запросов нет; ошибка Google не мешает
  сохранению профиля.

## 4. Спеки и документация

- [x] 4.1 `openspec/changes/shift-schedule-on-timezone-change/`:
  `proposal.md`, `design.md`, `tasks.md`, дельты `tutor-timezone`
  (замена «Смена зоны не меняет данные» на «Смена зоны сохраняет
  настенное время расписания»), `tutor-profile-settings`,
  `slot-management`, `homework-management`, `student-finance`.
- [x] 4.2 `CHANGELOG.md`, `[Unreleased]` → «Изменено»: смена часового
  пояса сохраняет настенное время занятий, окон, сроков ДЗ и списаний.
- [x] 4.3 Синхронизировать main-спеки при архивации change'а
  (`openspec archive shift-schedule-on-timezone-change`).

## 5. Регресс

- [x] 5.1 `uv run pytest tests/test_timezone_shift.py tests/test_gcalendar_sync.py
  tests/test_profile.py tests/test_lesson_pages.py` — зелёные.
- [x] 5.2 `uv run pytest -n auto` — весь набор зелёный (2158 passed).
- [x] 5.3 `openspec validate shift-schedule-on-timezone-change --strict`.
- [x] 5.4 Линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/
  main.py cron.py` — без новых ошибок.

## 6. Контракт стенда

- [x] 6.1 `.taskdesk/stand.toml` — `up`, `port_env = "PORT"`,
  `health_path = "/health"`, `[stand.env]` с `DATABASE_URL` и `TZ`;
  отдельная БД не нужна (приложение на SQLite).
- [x] 6.2 `.taskdesk/stand-up.sh` — `uv sync --frozen --no-dev`,
  `alembic upgrade head`, затем `uvicorn` на `$PORT`; проверено:
  `/health` → 200.

## Workflow follow-up

- Архив change'а — после ревью.
