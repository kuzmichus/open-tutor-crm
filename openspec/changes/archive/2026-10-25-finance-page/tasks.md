# Tasks

## 1. Сервисы

- [x] 1.1 `app/finance/services/periods.py`: разбор `period` (month/prev/3m/all) в окно
      UTC в зоне педагога + подпись периода.
- [x] 1.2 `app/finance/services/summary.py`: поток за период (доход, возвраты, чистый
      доход, заработано уроками), расходы-заглушка, прибыль, долги и переплаты по балансам,
      сравнение «заработано и получено».
- [x] 1.3 `app/finance/services/income_dialog.py`: контекст диалога платежа с выбором
      ученика (варианты `data-options`, значения при повторной отрисовке).

## 2. Views и подключение

- [x] 2.1 `app/finance/views/index.py`: `GET /tutor/finance` — страница с периодом.
- [x] 2.2 `app/finance/views/summary.py`: `GET /tutor/finance/summary` — партиал сводки.
- [x] 2.3 `app/finance/views/income_new.py`: `GET /tutor/payments/new` — диалог
      с выбором ученика (статический путь до `/tutor/payments/{payment_id}`).
- [x] 2.4 `app/finance/views/income_create.py`: `POST /tutor/payments` — создание
      платежа; пустой ученик — ошибка валидации, чужой — 404; без JS — 303 на страницу.
- [x] 2.5 Сборка роутера `app/finance/views/__init__.py` (порядок: статические раньше
      параметрических).

## 3. Шаблоны, JS и стили

- [x] 3.1 `finance/index.html`: шапка с кнопками «Доход»/«Расход»-заглушкой, селектор
      периода, контейнер `#finance-summary`, `#modal-payment`.
- [x] 3.2 `finance/_summary.html`: восемь карточек и блок «Заработано и получено»;
      перезапрос по `payment-saved`.
- [x] 3.3 Правка `finance/_payment_dialog.html`: режим выбора ученика (`payment_student`
      отсутствует) — пикер + скрытый `student_id`.
- [x] 3.4 `payments.js`: фабрика `incomeStudentPicker` (выбор ученика в диалоге).
- [x] 3.5 `styles.css`: блок `fin-*` (карточки, тулбар, селектор периода) на токенах.

## 4. Тесты и документация

- [x] 4.1 `tests/test_finance_page.py`: вход без сессии, сводки за период (платежи,
      статусы, возвраты, списания), долги/переплата, периоды (prev/3m/all/мусор),
      диалог «Доход» (пикер, пустой ученик — ошибка, чужой ученик — 404, успех —
      `payment-saved` и 303 без JS), изоляция по репетитору, «Расход» — заглушка.
- [x] 4.2 README: раздел «Финансы».
- [x] 4.3 Спека `tutor-finance` (delta в change).
