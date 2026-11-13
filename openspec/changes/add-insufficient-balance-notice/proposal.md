# Proposal

## Why

Репетитор видит, что ученику не хватает денег на занятие, только когда
откроет счёт ученика или получит утреннюю сводку в мессенджер. Если
мессенджеры не подключены, а урок сегодня — о долге можно узнать уже после
занятия. Сейчас в кабинете есть баннер «N уроков не отмечены», но денежного
напоминания на странице нет, хотя все данные для него уже посчитаны.

## What Changes

- Новый сервис `app/lesson/services/balance_notice.py`:
  `today_balance_notice(db, tutor, day=None)` — запланированные уроки дня
  берутся из `daily_digest.digest_lessons()`, нехватка по каждому ученику
  считается через `finance.services.balance.shortfall()` от суммы цен его
  целей за день.
- Новый партиал `GET /tutor/notices/balance` (`app/lesson/views/balance_notice.py`
  + шаблон `app/lesson/templates/lesson/_balance_notice.html`): красная плашка
  «Сегодня занятие у 1 ученика, а на счёте не хватает 1 500 ₽», ссылка
  «Открыть» на `/tutor/students?debtors=1` и крестик закрытия.
- Подпись `balance_notice_label(count, missing)` в
  `app/finance/services/presentation.py` (родительный падеж после «у», деньги
  через `money()`), зарегистрирована в шаблонных хелперах.
- Контейнер `#tutor-balance-notice` в `app/templates/_notice_banner.html`:
  включается во все страницы кабинета, перезапрашивается по `lesson-saved`,
  `payment-saved` и `student-saved`.
- Стиль `.notice-banner--danger` на токене `--destructive`.
- Тесты `tests/test_balance_notice.py`: подпись и суммы, статусы и даты
  уроков, групповой урок, изоляция, ключ закрытия, контейнер на страницах.
- Спека `student-finance` (требование «Напоминание о нехватке средств на
  сегодняшние занятия») и ссылка из `lesson-management`.

**Вне области:**

- Мессенджеры и флаг `notify_insufficient_funds` не меняются: плашка на
  странице — независимое от сводки поведение.
- Схема БД и миграции не меняются: новых полей нет.

## Impact

- `app/lesson/services/balance_notice.py`, `app/lesson/views/balance_notice.py`,
  `app/lesson/views/__init__.py`, `app/lesson/templates/lesson/_balance_notice.html`;
- `app/finance/services/presentation.py`, `app/templates/_notice_banner.html`,
  `app/static/styles.css`;
- `tests/test_balance_notice.py`;
- `openspec/specs/student-finance/spec.md`,
  `openspec/specs/lesson-management/spec.md`, `CHANGELOG.md`, `README.md`.
