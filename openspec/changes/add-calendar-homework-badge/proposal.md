# Proposal

## Why

На странице календаря репетитор видит карточки уроков, но не видит, задано ли
по уроку домашнее задание и в каком оно статусе. Приходится открывать урок или
вкладку «Домашние задания», чтобы вспомнить, что задано, сдано или проверено.
В кабинете ученика такой значок уже есть — он экономит один клик и сразу
показывает состояние ДЗ.

## What Changes

- В карточке урока календаря репетитора появляется значок домашнего задания —
  та же иконка `book-open`, что в кабинете ученика.
- Цвет значка кодирует статус ДЗ: «Задано» — нейтральный, «Сдано» — акцентный,
  «Проверено» — зелёный, «Не выполнено» — красный.
- Просроченное ДЗ (срок сдачи прошёл, а статус всё ещё «Задано») показывается
  красным залитым значком с подписью «Просрочено»; флаг «Учитывать дедлайн»
  выключает автоматическую просрочку. «Сдано» и «Проверено» с прошедшим
  сроком просроченными не считаются.
- Статус «Не задано» и отсутствие записи ДЗ значок не показывают: пустая запись
  не является домашним заданием.
- Подпись статуса уходит в `title`/`aria-label` значка, а карточка в
  `title` дополняется суффиксом «· ДЗ: <подпись>».
- Состояния ДЗ недели загружаются одним SELECT на всю неделю (без N+1 на
  карточку), правило «Не задано не показываем» и карты классов/подписей
  выносятся в общий домен `app/homework/services`, чтобы календарь и кабинет
  не дублировали их.

## Capabilities

### New Capabilities

— (нет)

### Modified Capabilities

- `calendar`: новое требование «Значок домашнего задания в карточке урока».

## Impact

- **Сервисы ДЗ**: `app/homework/services/by_lesson.py` (`HIDDEN_STATUSES`,
  `OPEN_STATUSES`, `LessonHomework.is_overdue`, `homework_states`,
  `homework_by_lesson`), `app/homework/services/presentation.py` (карты
  статусов, виртуальное состояние `overdue`, подписи, классы, регистрация
  Jinja-хелперов).
- **Календарь**: `app/calendar/services/schedule_event.py` (поле
  `homework_status`), `app/calendar/services/week_days.py` (одна выборка
  статусов на неделю), `app/calendar/services/presentation.py`
  (`homework_status`/`homework_label` в представлении карточки).
- **Шаблон**: `app/calendar/templates/calendar/_area.html`.
- **Стили**: `app/static/styles.css` (`.cal-event__head`, существующие
  `.cal-hw-badge*` переиспользуются).
- **Кабинет**: `app/cabinet/services/calendar.py`,
  `app/cabinet/services/homework.py`, `app/cabinet/services/child_homework.py`,
  `app/cabinet/services/presentation.py` — переходят на общие сервисы ДЗ,
  поведение не меняется.
- **Тесты**: `tests/test_calendar.py`, `tests/test_cabinet_calendar.py`,
  `tests/test_homework.py`.
- **Спецификации**: `openspec/specs/calendar/spec.md` — после синхронизации
  delta-spec.
- **CHANGELOG.md**: строка в `[Unreleased] → Добавлено`.
- **Вне объёма**: отдельный статус «Просрочено» и расчёт по `due_at`;
  `deadline_enabled` на значок не влияет.
