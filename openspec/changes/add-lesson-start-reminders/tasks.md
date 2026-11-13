# Tasks

## 1. Данные и модель

- [x] 1.1 `app/lesson/models/lesson_reminder.py`: `LessonReminder`
  (`lesson_id` FK CASCADE, `offset_min`, `audience`, `recipient_id`,
  `channel`, `claimed_at`, `delivered_at`; UNIQUE «урок + интервал +
  получатель + канал», CHECK по `REMINDER_OFFSETS`, `REMINDER_AUDIENCES`
  и `MESSENGERS`).
- [x] 1.2 `app/models.py`: импорт-регистратор модели.
- [x] 1.3 Autogenerate-миграция `lesson_reminders`, `alembic upgrade head`
  и `alembic check`.
- [x] 1.4 Миграция `lesson_reminders` на пофайловую (по каналу) доставку:
  `channel`, `claimed_at`, `delivered_at` вместо `sent_at`; старые маркеры
  пересоздаются, потому что канал в них не сохранён.

## 2. Отбор уроков

- [x] 2.1 `app/lesson/services/reminder_student.py` и
  `reminder_lesson.py`: dataclass-ы получателя и урока.
- [x] 2.2 `app/lesson/services/reminder_lessons.py`: `upcoming_lessons` —
  запланированные уроки в окне 24 часов, цель из ученика или группы,
  участники группы с `remind_lesson = true` одним запросом.

## 3. Задание cron

- [x] 3.1 `app/messenger/services/lesson_reminders.py`: тексты
  (`Через 15 минут` / `Через 1 час` / `Завтра`, «13 ноября в 09:30»),
  `due_offsets`, отправка во все каналы репетитора и ученика.
- [x] 3.2 Захват доставки в канал коммитится до сетевого вызова,
  `delivered_at` — после успешной отправки; просроченный захват
  перехватывается через `REMINDER_CLAIM_LEASE`. Сбой одного репетитора —
  лог и откат, ошибка канала не блокирует остальные каналы и получателей.
- [x] 3.3 Регистрация `messenger.lesson_reminders` в
  `app/common/services/cron.py`.

## 4. Тесты и документация

- [x] 4.1 `tests/test_lesson_reminders.py`: реестр cron, интервалы 15/60/1440,
  точный текст репетитору и ученику, группа, часовые пояса, отключённые
  переключатели и интервалы, ученик без каналов.
- [x] 4.2 Идемпотентность, пропущенный тик, отменённый урок, изоляция
  чужого репетитора и чужого ученика в группе, сбой одного канала и его
  повтор после аренды захвата, наложившиеся прогоны (UNIQUE по каналу).
- [x] 4.3 `README.md` (раздел cron) и `CHANGELOG.md`.