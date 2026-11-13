# Tasks

## 1. Расчёт и подпись

- [x] 1.1 `app/lesson/services/balance_notice.py`:
  `today_balance_notice(db, tutor, *, day=None) -> dict | None` — уроки из
  `digest_lessons`, агрегация цен по ученику, `shortfall` от суммы.
- [x] 1.2 `app/finance/services/presentation.py`:
  `balance_notice_label(count, missing)` и регистрация в
  `register_template_helpers()`; общее правило склонения — `_plural()`
  (им же пользуется `lessons_count_label`).

## 2. Партиал и контейнер

- [x] 2.1 `app/lesson/views/balance_notice.py`: `GET /tutor/notices/balance`,
  пустое тело без данных, ключ закрытия
  `debt:<day>:<ids>#<missing>` (день педагога — от замечания ревью №2).
- [x] 2.2 `app/lesson/views/__init__.py`: подключить роутер рядом с `notices`.
- [x] 2.3 `app/lesson/templates/lesson/_balance_notice.html`: красная плашка,
  иконка `wallet`, ссылка «Открыть» на фильтр нехватки, крестик.
- [x] 2.4 `app/templates/_notice_banner.html`: контейнер
  `#tutor-balance-notice` перед контейнером не отмеченных уроков.
- [x] 2.5 `app/static/styles.css`: `.notice-banner--danger` и подсветка
  крестика на токене `--destructive`.
- [x] 2.6 `app/student/services/insufficient.py` + `student/views/index.py`,
  `student/views/list_partial.py`: фильтр `shortfall=1` — ученики, которым не
  хватает на сегодняшние занятия (критерий из `today_balance_notice`).
- [x] 2.7 `app/student/templates/student/_list.html` и `index.html`: плашка
  активного фильтра со сбросом, скрытое поле формы для поиска/сортировки,
  `.students-filter*` в `styles.css`.

## 3. Тесты

- [x] 3.1 `tests/test_balance_notice.py`: подпись, сумма нехватки, ссылка,
  разметка опасной плашки.
- [x] 3.2 Статусы и даты: завтра, вчера, «Проведён», «Отменён», «Перенесён»,
  цена не задана, денег хватает — пустое тело.
- [x] 3.3 Несколько учеников, два урока одного ученика, групповой урок,
  изоляция по репетитору.
- [x] 3.4 Ключ закрытия следует за днём, составом и суммой; контейнер есть на
  страницах кабинета; без сессии — редирект на вход.
- [x] 3.5 Адресат ссылки «Открыть»: ученик с положительным, но недостаточным
  балансом виден в фильтре `shortfall=1`; оплатившие и ученики без уроков —
  нет; изоляция по репетитору; фильтр сохраняется в партиале списка.
- [x] 3.6 Склонение подписи: «1 занятие / 2 занятия», «1 ученика / 2 учеников,
  21 ученика, 11 учеников» (`tests/test_finance_presentation.py`).

## 4. Документация

- [x] 4.1 `openspec/specs/student-finance/spec.md`: требование
  «Напоминание о нехватке средств на сегодняшние занятия» со сценариями.
- [x] 4.2 `openspec/specs/lesson-management/spec.md`: ссылка из требования о
  не отмеченных уроках.
- [x] 4.3 `CHANGELOG.md` и `README.md`: пользовательское описание плашки.
