# Tasks

## 0. Предпосылки

- [x] 0.1 Влить ветку TOCRM-42 (`add-payer-type-toggle-TOCRM-42`): деление
  дохода по типам опирается на `students.payer_type`, своего поля в этой
  ветке не добавляем. Проверка: `students.payer_type` в модели и зелёный
  `uv run pytest`.
- [x] 0.2 Опираться на настройки НПД из TOCRM-43 (`add-npd-settings`,
  вкладка «Финансы» профиля): `npd_enabled`, `npd_tax_rate_individual`,
  `npd_tax_rate_legal_entity`, `npd_annual_income_limit`. Своих колонок,
  DEFAULTS-ключей и миграций в этой ветке нет — после ребейза дубли
  (собственный флаг `is_npd_payer`, ставки в базисных пунктах и миграция
  `4d8e2f6a9c13`) удалены. Проверка: `uv run alembic heads` — одна голова
  `b7d24c9e5f10`.

## 1. Расчёт налога

- [x] 1.1 `app/finance/services/npd.py`: `earned_split` (один запрос
  `GROUP BY payer_type`, NULL и мусор → физлица), `tax_amount` (`Decimal`,
  половина вверх), `tax_context`, `ytd_income` (календарный год в зоне
  педагога), `limit_context` (проценты, полоса 0..100, предупреждение с
  80 %), `legal_insight` (доля юрлиц > 30 %), `npd_context` (при выключенном
  флаге — `{"enabled": False}` без запросов).
- [x] 1.2 `app/finance/services/presentation.py`: `npd_rate_label`
  (`Decimal`-проценты → «4 %», «4,5 %»), регистрация в
  `register_template_helpers`.
- [x] 1.3 `app/finance/services/summary.py`: ключи `npd`, `net_after_tax`,
  `net_after_tax_is_negative`; прежние ключи не меняются.

## 2. Шаблоны и стили

- [x] 2.1 `app/finance/templates/finance/_npd.html`: итог, детализация,
  сноска, прогресс-бар лимита с `role="progressbar"`, жёлтое предупреждение,
  подсказка про юрлиц.
- [x] 2.2 `_summary.html`: четвёртая карточка «Чистая прибыль (после налогов)»
  сразу за «Чистой прибылью», налоговая строка и итог «с учётом налогов»,
  `include` блока НПД после карточек, обновлённая шапка-документация.
- [x] 2.3 `app/static/styles.css`: `.fin-kpis--npd`, `.fin-compare--tax` и
  блок `.fin-npd*` на токенах темы; инлайновая ширина полосы.

## 3. Тесты

- [x] 3.1 `tests/test_finance_npd.py`: флаг выключен — страница прежняя;
  налог 800 + 600 = 1 400; карточка и итог блока сравнения; пример
  20 000 − 5 000 − 1 000 = 14 000; отрицательная прибыль; четыре карточки
  яруса; ставки и лимит из настроек; предупреждение и его отсутствие;
  календарный год против периода; подсказка про юрлиц при 40 % и 20 %;
  изоляция репетиторов; партиал htmx.
- [x] 3.2 Настройки НПД в тестах задаются полями TOCRM-43
  (`npd_enabled`, `npd_tax_rate_individual`, `npd_annual_income_limit`).
- [x] 3.3 Полный прогон `uv run pytest` — зелёный, включая
  `tests/test_css_styles.py` и `tests/test_icons_bundle.py`.

## 4. Документация

- [x] 4.1 Delta-спека `tutor-finance` в change-е: блок налога, состав,
  расчёт по типу плательщика, годовой лимит, подсказка про юрлиц и
  изменения «Сводки за период».
- [x] 4.2 `openspec/specs/tutor-finance/spec.md` — требования
  синхронизированы; `tutor-profile-settings` не меняется (настройки НПД —
  зона TOCRM-43).
- [x] 4.3 `CHANGELOG.md` — запись в `[Unreleased] → Добавлено`.
- [x] 4.4 `README.md` — строка про «Финансы» дополнена налогом НПД и лимитом
  самозанятого.
