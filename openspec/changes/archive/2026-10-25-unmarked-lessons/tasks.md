# Tasks

## 1. Правило «не отмечен» (`lesson`)

- [x] 1.1 Написать `app/lesson/services/unmarked.py`: `is_unmarked(lesson, *, now)` — «Запланирован» и уже закончился; `list_unmarked(db, tutor_id, tutor, *, now)` — выборка с именами целей (JOIN ученика и группы, изоляция по репетитору, свежие сверху); грубый SQL-префильтр `starts_at < now`, финально решает предикат в Python
- [x] 1.2 Хелперы подписей в `app/lesson/services/presentation.py`: русская плюрализация «N урок(а/ов) не отмечен(ы)» и формат «24 окт., 23:30»; регистрация в `templating.py`

## 2. Баннер на страницах кабинета

- [x] 2.1 Эндпоинт `app/lesson/views/notices.py`: `GET /tutor/notices` (`?explain=1` — пояснение на главной), без не отмеченных — пустое тело; зарегистрировать в `views/__init__.py`
- [x] 2.2 Партиал `lesson/_notices.html` (иконка, подпись, «Открыть» → `/tutor/lessons?status=unmarked`, кнопка закрытия, Alpine `noticeBanner` с ключом-состоянием) и общий контейнер `app/templates/_notice_banner.html` (`hx-trigger="load, lesson-saved from:body"`)
- [x] 2.3 `app/static/notices.js` (закрытие в `localStorage` по ключу) и подключение в `base.html` до Alpine
- [x] 2.4 Включить контейнер на страницы кабинета: главная (`explain=1`), профиль, календарь, ученики, карточка ученика, группы, уроки
- [x] 2.5 CSS: токены `--warning-soft`/`--warning-border`/`--warning-fg` (light + dark) и блок `.notice-banner` в `styles.css`

## 3. Фильтр «Не отмеченные» в списке уроков

- [x] 3.1 `services/lessons.py`: `FILTER_STATUSES`, `normalize_status`, параметр `status` в `list_lessons` (через `is_unmarked`)
- [x] 3.2 Вьюхи `index.py` и `list_partial.py`: чтение и нормализация `status`, передача в сервис и шаблон
- [x] 3.3 Шаблоны: селект статуса в `lesson/index.html` (в `hx-trigger` формы), учёт фильтра в empty-state `_table.html`

## 4. cron и автозавершение

- [x] 4.1 `app/lesson/services/auto_complete.py`: `AUTO_COMPLETE_AFTER = 24ч`, `overdue_lessons` (SQL-префильтр `starts_at <= отсечка` + предикат), `auto_complete_finished_lessons` — статус «Проведён» + `sync_lesson_charge`, без коммита
- [x] 4.2 `app/common/services/cron.py`: реестр `TASKS` и `run_tasks()` — задача в своей транзакции, коммит у runner, падение не мешает остальным, возврат 1 при падении
- [x] 4.3 `cron.py` в корне: `logging.basicConfig` + `run_tasks()`; README — команда запуска раз в минуту

## 5. Тесты и спеки

- [x] 5.1 `tests/test_lesson_notices.py`: показ/отсутствие баннера, плюрализация, пояснение только на главной, изоляция, редирект без сессии, контейнеры на страницах
- [x] 5.2 `tests/test_lessons_unmarked_filter.py`: фильтр на странице и в партиале, комбинация с поиском, неизвестное значение, будущие/проведённые не попадают
- [x] 5.3 `tests/test_lesson_auto_complete.py`: завершение + списание, границы 24 часов, групповой урок, проведённый и будущий не трогаются
- [x] 5.4 `tests/test_cron.py`: `run_tasks` выполняет и коммитит, код возврата, изоляция падения (rollback упавшей, выполнение остальных)
- [x] 5.5 Обновить `openspec/specs/lesson-management/spec.md` (три новых требования) и README (напоминания, фильтр, cron)
