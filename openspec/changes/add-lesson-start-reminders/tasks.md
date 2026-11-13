# Tasks

## 1. Данные и модель

- [x] 1.1 `app/lesson/models/lesson_reminder.py`: `LessonReminder`
  (`lesson_id` FK CASCADE, `offset_min`, `audience`, `recipient_id`,
  `sent_at`; UNIQUE «урок + интервал + получатель», CHECK по
  `REMINDER_OFFSETS` и `REMINDER_AUDIENCES`).
- [x] 1.2 `app/models.py`: импорт-регистратор модели.
- [x] 1.3 Autogenerate-миграция `lesson_reminders`, `alembic upgrade head`
  и `alembic check`.

## 2. Отбор уроков

- [x] 2.1 `app/lesson/services/reminder_student.py` и
  `reminder_lesson.py`: dataclass-ы получателя и урока.
- [x] 2.2 `app/lesson/services/reminder_lessons.py`: `upcoming_lessons` —
  запланированные уроки в окне 24 часов, цель из ученика или группы,
  участники группы с `remind_lesson = true` одним запросом.

## 3. Задание cron

- [x] 3.1 `app/messenger/services/lesson_reminders.py`: тексты
  (`Через 15 минут` / `Через 1 час` / `Завтра`, «13 ноября в 09:30»),
  `due_offsets`, маркеры, отправка во все каналы репетитора и ученика.
- [x] 3.2 Коммит после каждого репетитора, сбой одного репетитора — лог и
  откат, ошибка канала не блокирует остальные.
- [x] 3.3 Регистрация `messenger.lesson_reminders` в
  `app/common/services/cron.py`.

## 4. Тесты и документация

- [x] 4.1 `tests/test_lesson_reminders.py`: реестр cron, интервалы 15/60/1440,
  точный текст репетитору и ученику, группа, часовые пояса, отключённые
  переключатели и интервалы, ученик без каналов.
- [x] 4.2 Идемпотентность, пропущенный тик, отменённый урок, изоляция
  чужого репетитора и чужого ученика в группе, сбой одного канала.
- [x] 4.3 `README.md` (раздел cron) и `CHANGELOG.md`.