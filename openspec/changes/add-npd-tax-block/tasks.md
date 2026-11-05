# Tasks

## 0. Предпосылка: тип плательщика ученика

- [x] 0.1 Влить ветку TOCRM-42 (`add-payer-type-toggle-TOCRM-42`) в
  `add-npd-tax-block-TOCRM-44`: деление дохода по типам опирается на
  `students.payer_type`, своего поля в этой ветке не добавляем. Проверка:
  `git merge-base --is-ancestor add-payer-type-toggle-TOCRM-42 HEAD`, зелёный
  `uv run pytest`.

## 1. Модель и миграции

- [x] 1.1 `app/tutor/models/tutor_settings.py`: константы
  `NPD_RATE_INDIVIDUAL_BP = 400`, `NPD_RATE_LEGAL_BP = 600`,
  `NPD_INCOME_LIMIT = 2_400_000`, `NPD_LIMIT_WARN_PERCENT = 80`,
  `NPD_RATE_MAX_BP = 5_000`; четыре ключа в `DEFAULTS` и четыре колонки
  (`is_npd_payer` Boolean NOT NULL, две ставки и лимит — Integer NOT NULL) с
  ORM-дефолтами.
- [x] 1.2 Merge-ревизия `9a1c7d3e5b20_merge_npd_heads.py`
  (`down_revision = ('5eb0e460963e', 'c3f1a9d7e2b4')`): склеивает две головы,
  схему не меняет.
- [x] 1.3 Ревизия `4d8e2f6a9c13_add_npd_settings.py`: четыре `op.add_column` с
  `server_default`, `downgrade` снимает их в обратном порядке. Проверка:
  `alembic heads` — одна голова, `upgrade head` / `downgrade -1` на чистой
  базе проходят.

## 2. Вкладка «Профиль»

- [x] 2.1 `app/tutor/services/profile_form.py`: `parse_profile_form` возвращает
  `(поля карточки, настройки НПД, ошибки)`; разбор флага, ставок (проценты →
  базисные пункты, запятая допустима, 0 < ставка ≤ 50 %) и лимита (целое > 0,
  пробелы внутри числа допускаются); маркер `npd_present` — без него настройки
  не трогаются.
- [x] 2.2 `app/tutor/services/profile_page.py`: `_form_defaults` для ветки
  `profile` дополняется флагом, ставками в процентах и лимитом.
- [x] 2.3 `app/tutor/views/profile_save.py`: новые поля формы, запись карточки
  и `save_settings` для НПД, 303 и ре-рендер с ошибками как раньше.
- [x] 2.4 Общий макрос переключателя `app/tutor/templates/tutor/_switch.html`;
  `_tab_notifications.html` и `_tab_profile.html` импортируют его
  `with context`.
- [x] 2.5 `_tab_profile.html`: карточка «Налог на профессиональный доход (НПД)»
  — переключатель, ставки с физлиц/юрлиц, годовой лимит, пояснения и
  дефолты.

## 3. Расчёт налога

- [x] 3.1 `app/finance/services/npd.py`: `earned_split` (один запрос
  `GROUP BY payer_type`, NULL и мусор → физлица), `tax_amount` (целочисленно,
  половина вверх), `tax_context`, `ytd_income` (календарный год в зоне
  педагога), `limit_context` (проценты, полоса 0..100, предупреждение с 80 %),
  `legal_insight` (доля юрлиц > 30 %), `npd_context` (при выключенном флаге —
  `{"enabled": False}` без запросов).
- [x] 3.2 `app/finance/services/presentation.py`: `npd_rate_label`
  (базисные пункты → «4 %», «4,5 %»), регистрация в `register_template_helpers`.
- [x] 3.3 `app/finance/services/summary.py`: ключи `npd`, `net_after_tax`,
  `net_after_tax_is_negative`; прежние ключи не меняются.

## 4. Шаблоны и стили

- [x] 4.1 `app/finance/templates/finance/_npd.html`: итог, детализация,
  сноска, прогресс-бар лимита с `role="progressbar"`, жёлтое предупреждение,
  подсказка про юрлиц.
- [x] 4.2 `_summary.html`: четвёртая карточка «Чистая прибыль (после налогов)»
  сразу за «Чистой прибылью», налоговая строка и итог «с учётом налогов»,
  `include` блока НПД после карточек, обновлённая шапка-документация.
- [x] 4.3 `app/static/styles.css`: `.fin-kpis--npd`, `.fin-compare--tax` и
  блок `.fin-npd*` на токенах темы; инлайновая ширина полосы.

## 5. Тесты

- [x] 5.1 `tests/test_finance_npd.py`: флаг выключен — страница прежняя;
  налог 800 + 600 = 1 400; карточка и итог блока сравнения; пример
  20 000 − 5 000 − 1 000 = 14 000; отрицательная прибыль; четыре карточки
  яруса; ставки и лимит из настроек; предупреждение и его отсутствие;
  календарный год против периода; подсказка про юрлиц при 40 % и 20 %;
  изоляция репетиторов; партиал htmx.
- [x] 5.2 `tests/test_profile.py`: дефолты 4 / 6 / 2 400 000 до первого
  сохранения, сохранение и повторный показ, выключение флага, ставки с
  запятой, ошибки (ставка 120, 0, лимит 0, мусор), частичный POST не сбрасывает
  настройки, сохранение профиля не затирает уведомления.
- [x] 5.3 Полный прогон `uv run pytest` — зелёный, включая
  `tests/test_css_styles.py` и `tests/test_icons_bundle.py`.

## 6. Документация

- [x] 6.1 Delta-спеки `tutor-finance` и `tutor-profile-settings` в change-е.
- [x] 6.2 `openspec/specs/tutor-finance/spec.md` и
  `openspec/specs/tutor-profile-settings/spec.md` — требования синхронизированы.
- [x] 6.3 `CHANGELOG.md` — запись в `[Unreleased] → Добавлено`.
- [x] 6.4 `README.md` — строка про «Финансы» дополнена налогом НПД и лимитом
  самозанятого.
