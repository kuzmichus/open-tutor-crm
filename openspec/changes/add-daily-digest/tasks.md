# Tasks

## 1. Общие правила (финансы и привязка)

- [x] 1.1 `app/finance/services/charges.py`: вынести выбор целей с ценами в
  публичную `lesson_targets_any_status(db, lesson)` и переиспользовать её в
  `lesson_targets` (после фильтра статуса и отметок отсутствия). Проверка:
  `uv run pytest tests/test_finance_charges.py tests/test_finance_lesson_charges.py` — зелёный.
- [x] 1.2 `app/finance/services/balance.py`: чистая функция
  `shortfall(balance_value, price) -> int` (0, если хватает или цена не задана;
  иначе `price − balance`). Проверка: `tests/test_finance_balance.py` — зелёный.
- [x] 1.3 `app/messenger/services/binding.py`: `bound_chats(db, tutor_id) ->
  dict[messenger, chat_id]` — привязанные чаты по `SUPPORTED` одним
  `all_params`. Проверка: `tests/test_notification_channels.py` — зелёный.

## 2. Данные сводки

- [x] 2.1 `app/lesson/services/digest_target.py` и `digest_lesson.py` — строки
  сводки (ученик с ценой; урок с целью, признаком группы и списком учеников).
  Проверка: импорт модулей, линт — чисто.
- [x] 2.2 `app/lesson/services/daily_digest.py`: `digest_lessons(db, tutor, day=None)`
  — «Запланированные» уроки дня педагога (окно `local_day_bounds`, JOIN
  `Student`/`Group`, изоляция по владельцу цели, порядок по `starts_at`), цели и
  цены через `charges.lesson_targets_any_status`, имена участников групп одним
  запросом с фильтром по `tutor_id`. Проверка: `tests/test_daily_digest.py`.

## 3. Задание cron

- [x] 3.1 `app/messenger/services/daily_digest.py`: `run_daily_digests(db, *,
  now=None) -> int` — отбор репетиторов с привязанным чатом, флаг
  `notify_daily_digest`, сравнение местного времени с `digest_time`, маркер
  `digest_sent_date`, отправка во все привязанные каналы, коммит на репетитора.
  Проверка: `tests/test_daily_digest.py`.
- [x] 3.2 Там же `build_digest_text(...)`: заголовок «Сводка уроков на
  ДД.ММ.ГГГГ», строки «ЧЧ:ММ — имя ученика/группы», подстроки о нехватке
  («не хватает N ₽ (на счету B ₽, урок P ₽)»), обрезка до 4000 символов.
- [x] 3.3 `app/common/services/cron.py`: импорт задания и запись
  `("messenger.daily_digest", run_daily_digests)` в `TASKS`, docstring про второе
  задание. Проверка: `tests/test_cron.py` — задание в реестре.

## 4. Тесты

- [x] 4.1 `tests/test_daily_digest.py`: реестр cron; отправка после `digest_time`
  во все привязанные каналы (urlopen подменён, проверяются URL, тело, число
  вызовов); до `digest_time` — тишина; повторный прогон в тот же день — тишина,
  на следующий день — отправка; своё время из профиля.
- [x] 4.2 Содержание: время и имя ученика/группы; пометка при `balance < price`
  и её отсутствие при достаточном балансе; цена участника группы
  (`price_override`) и общая цена группы; `notify_insufficient_funds=False`
  убирает пометку; `notify_daily_digest=False` отключает сводку; проведённые
  уроки в сводку не попадают.
- [x] 4.3 Края и изоляция: чужой репетитор в выборку не попадает; репетитор без
  привязанных чатов — без сети; уроков нет — сообщения нет, маркер дня поставлен;
  часовой пояс (`Asia/Tokyo`) сдвигает момент отправки и показ времени; ошибка
  одного канала не мешает второму; длинная сводка обрезается.
- [x] 4.4 `tests/test_cron.py`: проверка наличия `messenger.daily_digest` в
  `TASKS`; существующие тесты не сломаны.

## 5. Документация

- [x] 5.1 `README.md` (раздел Cron): описать второе задание — дневная сводка по
  времени из профиля во все привязанные мессенджеры.
- [x] 5.2 `CHANGELOG.md` (Unreleased): строка «Дневная сводка уроков в мессенджеры».

## 6. Проверки

- [x] 6.1 `uv run pytest -n auto` — набор зелёный, кроме
  `tests/test_finance_invoice.py` (6 тестов красные и без изменений задачи:
  зависят от текущей даты).
- [x] 6.2 Линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py` —
  чисто.
- [x] 6.3 Миграции не нужны (схема не менялась), `alembic check` дрейфа не даёт.

## Workflow follow-up

- Синхронизировать и архивировать change после ревью.
