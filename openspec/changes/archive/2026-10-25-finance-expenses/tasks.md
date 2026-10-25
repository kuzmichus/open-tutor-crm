# Tasks

## 1. Модель и миграция

- [x] 1.1 `app/finance/models/expense.py`: `Expense` + `EXPENSE_CATEGORIES`/
      `EXPENSE_CATEGORY_LABELS` (CHECK по закрытому списку), импорт в `app/models.py`.
- [x] 1.2 Миграция `49508a25c7c2_add_expenses` (autogenerate, применена).

## 2. Сервисы

- [x] 2.1 `expense_form.py`: разбор/валидация (сумма > 0, дата, категория, комментарий).
- [x] 2.2 `expense_writer.py`: создание, `spent_at` = дата + время зоны педагога → UTC.
- [x] 2.3 `expense_dialog.py`: контекст диалога с умолчаниями и повторной отрисовкой.
- [x] 2.4 `expenses.py`: сумма и список трат за окно периода.
- [x] 2.5 `balances.py`: ненулевые балансы учеников (имена, инициалы) одной формулой
      с `signed_amount`.
- [x] 2.6 `operations_feed.py`: строки ленты (платежи/возвраты/расходы), табы
      и их разбор.
- [x] 2.7 `operations_section.py`: общий контекст секции для страницы и партиала.
- [x] 2.8 `summary.py`: реальные расходы, `profit`, `left_for_tutor`; `access.py`:
      `get_owned_expense`; `presentation.py`: `expense_category_label`.

## 3. Views, шаблоны, стили

- [x] 3.1 `expense_new.py` (GET `/tutor/expenses/new`), `expense_create.py`
      (POST `/tutor/expenses`: ошибки — повторный диалог, успех — `expense-saved`,
      без JS — 303), `operations.py` (GET `/tutor/finance/operations`).
- [x] 3.2 `index.py`: вкладка из query, контекст секции операций.
- [x] 3.3 Шаблоны: `_expense_dialog.html`, `_operations.html` (табы, таблица,
      заглушки, карточка балансов), правка `_summary.html` (− Расходы,
      = Осталось репетитору, событие `expense-saved`) и `index.html`
      (активная кнопка «Расход», `#modal-expense`, скрытый `tab`).
- [x] 3.4 `payments.js`: фабрика `expenseDialog` (контейнер `#modal-expense`).
- [x] 3.5 `styles.css`: `fin-operations`/`fin-ops`/`fin-balances`, модификаторы
      `fin-compare`, бейджи статусов — плоские BEM-селекторы на токенах.

## 4. Тесты и документация

- [x] 4.1 `tests/test_finance_expenses.py`: вход без сессии, поля диалога и
      категории, создание (успех/ошибки/без JS), сводка с расходами и
      «Осталось репетитору», период, партиалы и события, табы (включая заглушки
      и мусор в query), фильтры ленты, пустое состояние, балансы (должники/
      переплата/пустая), изоляция по репетитору.
- [x] 4.2 Правка `tests/test_finance_page.py`: кнопка «Расход» открывает диалог,
      `hx-trigger` сводки с двумя событиями.
- [x] 4.3 Спека `tutor-finance` (delta в change), README.
