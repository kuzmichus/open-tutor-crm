# Tasks

## 1. Клиентская группа плашек

- [x] 1.1 `app/static/notices.js`: Alpine-фабрика `noticeGroup` — `expanded`
  (из `localStorage["opentutorcrm:notices-expanded"]`), `count`,
  `recount()`, `toggle()`, `scheduleRecount()`, `init()`/`destroy()`.
- [x] 1.2 `recount()` считает `.notice-banner` внутри `$el` с
  `style.display !== "none"` — закрытая крестиком плашка из счёта выпадает.
- [x] 1.3 `MutationObserver` на поддереве (`childList`, `subtree`,
  `attributes` + `attributeFilter: ["style"]`) с дебаунсом через
  `queueMicrotask`; отключение в `destroy()`.

## 2. Разметка и стили

- [x] 2.1 `app/templates/_notice_banner.html`: группа
  `#tutor-notice-stack` с `x-data="noticeGroup"`, оба существующих контейнера
  внутри `.notice-stack__items`, их `hx-get`/`hx-trigger`/`hx-swap` не
  меняются.
- [x] 2.2 Сводка `.notice-summary` с `x-show="count > 1"` и `x-cloak`:
  иконка, «Требует внимания», `·`, счётчик, кнопка «Показать»/«Свернуть»,
  `chevron-down` с поворотом.
- [x] 2.3 `app/static/styles.css`: `.notice-summary`, `.notice-summary__icon`,
  `.notice-summary__title`, `.notice-summary__dot`, `.notice-summary__count`,
  `.notice-summary__toggle`, `.notice-summary__chevron`,
  `.notice-summary__chevron--open`, `.notice-stack__items` — плоские
  BEM-селекторы на токенах `--warning-*`, `flex-wrap: wrap` у сводки.

## 3. Тесты

- [x] 3.1 `tests/test_notice_stack.py`: на страницах кабинета есть группа,
  сводка со счётчиком и действием, оба контейнера внутри
  `.notice-stack__items`, сводка — вне скрываемого блока.
- [x] 3.2 `x-cloak` есть у сводки и нет у контейнера плашек.
- [x] 3.3 Контракт `notices.js`: фабрика, ключ `opentutorcrm:notices-expanded`,
  `MutationObserver`, подсчёт видимых плашек, `disconnect()`.
- [x] 3.4 Все классы сводки описаны в `styles.css`, у `.notice-summary` есть
  `flex-wrap: wrap`.
- [x] 3.5 Регрессии партиалов: ровно одна плашка со своими текстами, сводки
  в ответе нет, пустое тело без данных, редирект без сессии.

## 4. Документация

- [x] 4.1 `openspec/specs/cabinet-notices/spec.md`: требование сводки со
  сценариями «0 / 1 / 2+», раскрытие-сворачивание, сохранение состояния,
  узкий экран.
- [x] 4.2 `openspec/changes/collapse-warning-banners/`: proposal, design,
  tasks, delta-спека, `.openspec.yaml`.
- [x] 4.3 `CHANGELOG.md` и `README.md`: пользовательское описание сводки.
