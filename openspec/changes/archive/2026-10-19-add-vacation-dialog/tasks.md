# Tasks

## 1. Меню быстрого добавления в панели

- [x] 1.1 В `_area.html`: кнопка `#cal-more` (иконка-кебаб, aria-haspopup/aria-expanded) сразу после `#cal-add`, выпадающее меню `#cal-more-menu` (паттерн `.cal-color`: `x-show` + `x-cloak` + `@click.outside` + Escape) с пунктами `#cal-add-slot` (переехавшая из тулбара прямая кнопка слота, ровно `@click="openSlotDialog()"`) и `#cal-add-vacation` (`@click="openVacationDialog()"`), каждый пункт закрывает меню; прямая кнопка слота из тулбара удалена; проверка: SSR-тест в `tests/test_calendar.py` — `#cal-more` идёт в разметке сразу после `#cal-add`, оба пункта внутри `#cal-more-menu`, атрибуты закрытия на месте, `openSlotDialog()` встречается в разметке ровно один раз (пункт меню), и существующий тест `test_calendar_slot_dialog_markup` проходит без правок (id и обработчик сохранены)
- [x] 1.2 В `calendar.js`: состояние `moreOpen`, `toggleMore()`/`closeMore()` (закрытие по Escape и клику вне — через атрибуты разметки), выбор любого пункта закрывает меню перед открытием диалога; проверка: статический тест — `moreOpen`, `toggleMore` и `closeMore` есть в `calendar.js`; `uv run pytest tests/test_calendar.py -q` зелёные

## 2. Диалог «Новый отпуск»

- [x] 2.1 Разметка диалога в `_area.html`: форма `#cal-vacation-form` с `@submit="createVacation($event)"`, обязательные поля `#vac-start` и `#vac-end` (`type="date"`, у конца `:min="vacationForm.start"`), кнопки «Отмена» (`closeVacation()`) и «Создать» (submit), заголовок «Новый отпуск», закрытие по Escape и backdrop; в `calendar.js` — состояние `vacationForm: { open, start, end }`, `openVacationDialog()` с префиллом от общего `prefillMoment()` (обе даты = ближайшая видимая, однодневный отпуск по умолчанию), `closeVacation()` со сбросом полей; проверка: SSR-тест — диалог «Новый отпуск» в разметке, два `type="date"` поля с `required`, `min`-привязка у `#vac-end`, кнопки «Отмена»/«Создать» и `createVacation($event)` присутствуют
- [x] 2.2 В `calendar.js`: `createVacation(event)` — `preventDefault()`, defensive-отказ при `end < start`, пересечение диапазона с `data-date` колонок сетки, вставка `<div class="cal-vacation">Отпуск</div>` первым ребёнком каждого попавшего дня (блок под карточками занятий), закрытие диалога, ноль сетевых запросов; проверка: статический тест — `createVacation`, `vacationForm`, `openVacationDialog`, `prefillMoment` и строка `"cal-vacation"` есть в `calendar.js`, `fetch(` и `XMLHttpRequest` отсутствуют; `uv run pytest tests/test_calendar.py -q` зелёные

## 3. Клик по отпуску не открывает форму урока

- [x] 3.1 В `calendar.js` guard в `openSlot()`: если в колонке дня есть `.cal-vacation` — форма урока не открывается (покрывает и клиентские блоки, и существующую демо-заглушку, чиня требование спеки `calendar`); проверка: статический тест — в теле `openSlot` присутствует проверка `.cal-vacation`; `uv run pytest tests/test_calendar.py -q` зелёные (старые тесты клика по четверти и модалки урока не сломаны)

## 4. Интеграционная проверка

- [x] 4.1 Полный прогон: `uv run pytest` — все тесты зелёные
- [x] 4.2 `openspec validate add-vacation-dialog --strict` — без ошибок; браузерный сценарий: кебаб ⋮ → меню (Escape и клик вне закрывают) → «Добавить отпуск» → диалог с префиллом → диапазон (включая «конец раньше начала» — форма не отправляется) → «Создать» → блоки «Отпуск» на дни недели, карточки занятий видны поверх, клик по отпуску не открывает форму урока, «Отмена» не меняет сетку → из меню «Добавить слот» → существующий диалог слота → листание недели убирает отпуск; результат зафиксировать комментарием в задаче
  <!-- Результат (2026-10-19, Chromium headless, http://127.0.0.1:8124):
       validate --strict → "Change 'add-vacation-dialog' is valid".
       Сценарий пройден полностью, 38/38 проверок (vacation-summary.md):
       #cal-more идёт в панели сразу после #cal-add (позиции 7/8), меню
       закрыто при загрузке, клик по ⋮ открывает #cal-more-menu с пунктами
       «Добавить слот»/«Добавить отпуск», aria-expanded=true; Escape и клик
       вне меню закрывают его, сетка без изменений. Пункт «Добавить
       отпуск» закрывает меню и открывает диалог «Новый отпуск», обе даты
       предзаполнены 2026-10-19 (ближайшая видимая, однодневный отпуск).
       Диапазон «конец раньше начала» (21.10 → 20.10): submit заблокирован
       нативной валидацией (:invalid у #vac-end), окно открыто, блоков нет,
       сетка без изменений. Валидный диапазон 19–21.10 → «Создать»: диалог
       закрыт, 0 XHR/fetch, блоки «Отпуск» первыми детьми колонок 19/20/21
       октября, дни вне диапазона без блоков; карточки занятий видны поверх
       и кликабельны (elementFromPoint попадает в .cal-event). Клик по
       четверти под отпуском не открывает форму урока (контроль: клик по
       четверти без отпуска открывает — guard работает избирательно);
       клик по серверной демо-заглушке отпуска (август) — тоже не открывает.
       Escape и «Отмена» закрывают диалог отпуска, сетка без изменений.
       Из меню «Добавить слот» → диалог «Новый слот», Escape закрывает.
       Листание на 26 октября – 1 ноября убирает блоки отпуска. Консоль
       браузера без ошибок. Артефакты: test-result/vacation-01-menu.png,
       vacation-02-dialog-prefill.png, vacation-03-invalid-range.png,
       vacation-04-created.png, vacation-05-slot-dialog.png,
       vacation-06-next-week.png, vacation-07-demo-vacation.png,
       vacation-scenario.mp4 (видео прогона). -->

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
- Verify the archived result.
