# Tasks

## 1. Правило занятости

- [x] 1.1 `app/lesson/models/lesson.py`: `NOT_HELD_STATUSES` из
  `cancelled` и `rescheduled`.
- [x] 1.2 `app/slot/services/busy.py::lessons_for_range`: исключить статусы
  через `Lesson.status.notin_(NOT_HELD_STATUSES)`; докстринг объясняет
  единую точку.
- [x] 1.3 `app/calendar/services/presentation.py` и
  `app/stats/services/new_and_trials.py`: переиспользовать константу вместо
  пары литералов.

## 2. Тесты

- [x] 2.1 `tests/test_slots.py`: отменённый и перенесённый уроки не делают
  окно занятым и не дают конфликта.
- [x] 2.2 `tests/test_slot_views.py`: окно создаётся и переносится на время
  отменённого/перенесённого урока.
- [x] 2.3 `tests/test_slot_batch.py`: такой урок не пропускает окно пачки.
- [x] 2.4 `tests/test_bookings.py`: бронь подтверждается поверх отменённого
  или перенесённого урока.

## 3. Документация

- [x] 3.1 `openspec/specs/slot-management/spec.md`: оговорка о статусе в
  требованиях о пересечениях, занятости, переносе и приёме заявки; сценарий
  «Отменённый урок освобождает окно».
- [x] 3.2 `CHANGELOG.md`: запись в `[Unreleased]`.