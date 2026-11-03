# Tasks

## 1. Источник значения

- [x] 1.1 `app/tutor/services/settings.py`: добавить
  `default_lesson_duration(db: Session, tutor_id: str) -> int` — значение
  `get_settings(...).default_lesson_duration`, если оно входит в
  `LESSON_DURATIONS`, иначе `DEFAULT_LESSON_DURATION` (60). Проверка:
  `uv run pytest tests/test_lesson_create.py tests/test_slot_views.py -k duration`.

## 2. Форма урока

- [x] 2.1 `app/lesson/services/lesson_form.py`: в `lesson_form_context` после
  `values = _form_values(...)` подставлять
  `default_lesson_duration(db, tutor.id)`, когда `lesson is None` и
  `values["duration_min"] is None`. Приоритет присланных данных и
  `?duration_min=` не менять. Проверка: `tests/test_lesson_create.py`.
- [x] 2.2 Обновить docstring `_form_values` и `lesson_form_context`: в
  создании без явной длительности подставляется настройка профиля, правка
  настройку не смотрит.

## 3. Диалог окна

- [x] 3.1 `app/slot/services/dialog_context.py`: считать
  `default_duration = default_lesson_duration(db, tutor.id)` один раз в
  `dialog_context` и передавать параметром в `_single_values` и
  `_batch_values` вместо чтения константы внутри. Проверка:
  `tests/test_slot_views.py`.
- [x] 3.2 Оставить `DEFAULT_DURATION_MIN = 40` аварийным значением и
  переписать комментарий: действующий дефолт — настройка профиля.
- [x] 3.3 Обновить docstring `dialog_context` — длительность нового окна в
  обоих режимах равна настройке профиля.

## 4. Тесты

- [x] 4.1 `tests/test_lesson_create.py`: настройка 45 → селект нового урока
  предвыбирает 45; без строки настроек → 60; `?duration_min=90` перекрывает
  настройку 45; мусор в настройке (61) → 60.
- [x] 4.2 `tests/test_lesson_update.py`: форма редактирования показывает
  длительность урока (90), а не настройку профиля (45).
- [x] 4.3 `tests/test_slot_views.py`: настройка 45 → option 45 selected в
  обоих режимах (`slot-new-duration`, `slot-batch-duration`); без строки
  настроек → 60; `?date=`/`?time=` настройку не сбрасывают; мусор в настройке
  (61) → 60.
- [x] 4.4 Регресс: `tests/test_calendar.py` (префилл 40 из окна остаётся
  приоритетным, `?duration_min=80` игнорируется), `tests/test_profile.py`
  (сохранение и показ настройки), `tests/test_slot_batch.py` — зелёные.

## 5. Документация

- [x] 5.1 `CHANGELOG.md`: строка в `## [Unreleased]` → «Изменено» —
  длительность новых уроков и окон по умолчанию берётся из «Длительности
  урока по умолчанию (мин)» на вкладке «Календарь».
- [x] 5.2 Полный прогон `uv run pytest -n auto` и линт
  `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py`.

## Workflow follow-up

- Синхронизация спек и архив change'а — после ревью
  (`openspec archive use-default-lesson-duration`).
