# Tasks

## 1. Общие сервисы

- [x] 1.1 `app/tutor/services/params.py`: `save_param(db, tutor_id, key, value)` —
  upsert без коммита; `set_param` реализован как `save_param` + `db.commit()`.
  Проверка: `uv run pytest tests/test_notification_channels.py tests/test_profile.py` — зелёный.
- [x] 1.2 Там же `all_params_by_tutors(db, tutor_ids)` — параметры пачки
  репетиторов одним запросом (`TutorParam.tutor_id.in_(...)`), без N+1.

## 2. Данные именинников

- [x] 2.1 `app/student/services/birthdays.py`: `birthday_students(db, tutor_id,
  day, *, include_archived=False)` — префильтр в SQL (`tutor_id`,
  `birth_date IS NOT NULL`, статус), сравнение месяца и дня в Python, порядок по
  `COALESCE(last_name, first_name)`, без фильтра по `kind`.
- [x] 2.2 Там же `age_on(birth_date, day) -> int | None` — исполняющийся возраст;
  `None`, если год рождения в будущем.
- [x] 2.3 `app/student/services/presentation.py`: `birthday_age_label(birth_date,
  day)` — «1 год» / «2 года» / «5 лет» / «11 лет» / «21 год», пустая строка при
  неизвестном возрасте. Проверка: `tests/test_birthday_digest.py` — зелёный.

## 3. Задание cron

- [x] 3.1 `app/messenger/services/birthday_digest.py`: `notify_birthday_digest(db,
  *, now=None) -> int` — настройки и параметры пачкой, фильтр `notify_birthday`,
  сравнение местного времени с `digest_time`, маркер `birthday_digest_date`,
  отправка во все привязанные каналы, коммит на репетитора, изоляция сбоя
  репетитора.
- [x] 3.2 Там же `birthday_message(students, day)` — заголовок «Дни рождения
  сегодня, 1 ноября:» и строки «• Иван Иванов — 12 лет» (без emoji, тон как у
  приветствия); при пустом списке не вызывается.
- [x] 3.3 `app/common/services/cron.py`: импорт задания и запись
  `("messenger.birthday_digest", notify_birthday_digest)` в `TASKS`, docstring
  реестра дополнен. Проверка: `tests/test_cron.py` — задание в реестре.

## 4. Тесты

- [x] 4.1 `tests/test_birthday_digest.py`, выборка: свой именинник попадает;
  чужой репетитор, ученик без даты, архивный и не-именинник — нет; взрослый
  попадает; сортировка по фамилии; 29 февраля в невисокосный год не попадает.
- [x] 4.2 Там же, подписи: `age_on` и плюрализация возраста; текст сообщения с
  заголовком и строками.
- [x] 4.3 Там же, поведение задания (urlopen подменён): отправка после
  `digest_time` во все привязанные каналы и две строки `sent_messages`; до
  времени — тишина; своё время из профиля; `notify_birthday=False` — тишина;
  повторный прогон в тот же день — тишина, следующий день — снова отправка;
  канал без `chat_id` пропускается; нет каналов — ни сети, ни маркера; пустой
  список — без сообщения, но с маркером; сбой канала не поднимает исключение;
  часовой пояс `Europe/Samara` сдвигает границу отправки.
- [x] 4.4 `tests/test_cron.py`: задание в `TASKS`; прогон `run_tasks()` коммитит и
  маркер дня, и запись в `sent_messages`; существующий тест изоляции падений
  остаётся зелёным.
- [x] 4.5 `tests/test_profile.py`: регресс вкладки «Уведомления» — `notify_birthday`
  по-прежнему сохраняется и показывается, новых полей нет.

## 5. Документация

- [x] 5.1 `README.md` (раздел Cron): к автозавершению уроков и дневной сводке
  добавлена рассылка дней рождения — условие `notify_birthday`, время
  `digest_time`, только привязанные каналы, пустой список не отправляется,
  29 февраля в невисокосные годы.
- [x] 5.2 `CHANGELOG.md` (Unreleased): строка «Рассылка «День рождения»».
- [x] 5.3 OpenSpec change `add-birthday-digest`: `proposal.md`, `design.md`,
  `tasks.md`, delta-спеки `messenger-integration` и `tutor-profile-settings`.

## 6. Проверки

- [x] 6.1 `uv run pytest -n auto` — набор зелёный.
- [x] 6.2 `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py` — чисто.
- [x] 6.3 `openspec validate add-birthday-digest --strict` — change валиден.
- [x] 6.4 Миграции не нужны (схема не менялась), `alembic check` дрейфа не даёт.

## Workflow follow-up

- Синхронизировать и архивировать change после ревью.
