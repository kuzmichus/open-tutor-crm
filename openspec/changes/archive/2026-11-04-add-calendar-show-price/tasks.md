# Tasks

## 1. Хранение флага

- [x] 1.1 `app/tutor/models/tutor_settings.py`: константа
  `DEFAULT_SHOW_CALENDAR_PRICE = True`, ключ `show_calendar_price` в
  `DEFAULTS`, колонка `show_calendar_price: Mapped[bool]` (`Boolean`,
  `nullable=False`, дефолт из `DEFAULTS`).
- [x] 1.2 Миграция `alembic/versions/a7d3e1f42b90_add_calendar_show_price.py`:
  `add_column(..., nullable=False, server_default='1')`,
  `down_revision = 'c4b7a1f90d21'`, `downgrade` — `drop_column`.
- [x] 1.3 Проверка: `uv run pytest tests/test_profile.py` — `get_settings` без
  строки в БД отдаёт `show_calendar_price is True`, сохранение вкладки
  «Календарь» флаг не сбрасывает.

## 2. Цена карточки, включая стоимость группы

- [x] 2.1 `app/finance/services/charges.py`: `group_totals(db, group_ids) ->
  dict[str, int]` — один запрос, сумма `price_override ??
  group.price_per_lesson` по участникам; группы без цен в словарь не
  попадают.
- [x] 2.2 `app/calendar/services/week_lesson.py`: поле `price: int = 0` с
  пояснением, что у группового урока это суммарная стоимость группы.
- [x] 2.3 `app/calendar/services/week.py::week_lessons`: собрать id групп
  недели и заполнить `price` — индивидуальный урок `lesson.price or 0`,
  групповой — из `group_totals`.
- [x] 2.4 `app/calendar/services/schedule_event.py::from_lesson`: параметр
  `price: int | None = None`, переданное значение важнее `lesson.price`,
  ORM-объект не мутируется.
- [x] 2.5 `app/calendar/services/week_days.py`: передавать `price=row.price`.
- [x] 2.6 Проверка: `tests/test_calendar.py` — групповой урок с ценой группы
  1000 и участником с `price_override` 1200 показывает 2200 ₽; группа без
  цен и индивидуальный урок без цены цены не показывают.

## 3. Флаг в отображении

- [x] 3.1 `app/calendar/services/presentation.py`: `show_price: bool = True`
  в `build_calendar_context`, `build_day_view`, `layout_events`,
  `build_event_view`, `_lesson_fields`; при `False` `price_label = ""`
  (нет блока цены и нет «₽» в `title`); ключ `show_price` в контексте
  шаблона.
- [x] 3.2 `app/calendar/views/index.py`: читать
  `settings.show_calendar_price`, передавать в контекст; сборка ответа
  недели вынесена в общий `week_response`.
- [x] 3.3 `app/calendar/views/show_price.py`: `POST
  /tutor/calendar/show-price`, `show_price: str = Form("")`, `start:
  str = Form("")`, `save_settings`, ответ `saved_response(request,
  "price-saved", "/tutor/calendar?start=<пн>")`; роутер подключён в
  `app/calendar/views/__init__.py`.

## 4. Разметка и клиент

- [x] 4.1 `app/calendar/templates/calendar/_area.html`: чекбокс «Показывать
  цену» на существующем классе `.checkbox` с `hx-post`,
  `hx-trigger="change"`, `hx-vals` с текущей неделей, `hx-swap="none"` и
  `checked` из `show_price`.
- [x] 4.2 `app/calendar/templates/calendar/index.html`: `price-saved
  from:body` в `hx-trigger` корня `#calendar-swap`.
- [x] 4.3 Проверить `app/static/calendar.js`: правок не требуется —
  флаг ходит через `hx-post`, а `applyColorMode` переписывает только
  `[hx-get^="/tutor/calendar"]`.

## 5. Тесты

- [x] 5.1 `tests/test_calendar.py`: флаг включён — цена есть в
  `.cal-event__price` и в `title`; флаг выключен — цены нет ни в карточке,
  ни в подсказке, имя цели и интервал на месте.
- [x] 5.2 `tests/test_calendar.py`: `group_totals` — сумма по участникам,
  группа без цен не в словаре, пустой вход и `None`/`""` в id.
- [x] 5.3 `tests/test_calendar.py`: `POST /tutor/calendar/show-price`
  сохраняет флаг, отдаёт `HX-Trigger: price-saved`, без `HX-Request` — 303
  на понедельник видимой недели; чужой репетитор флаг не меняет; чекбокс в
  разметке отражает сохранённое состояние.
- [x] 5.4 `tests/test_calendar.py`: обновлена проверка подписок
  `#calendar-swap` — добавлен `price-saved`.
- [x] 5.5 `tests/test_profile.py`: дефолт флага и сохранение вкладки
  «Календарь» без сброса флага.

## 6. Регресс и документация

- [x] 6.1 `uv run pytest -n auto` — весь набор зелёный (2081 тест).
- [x] 6.2 Линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/
  main.py cron.py` — без ошибок.
- [x] 6.3 `openspec validate add-calendar-show-price --strict` — валиден.
- [x] 6.4 `CHANGELOG.md`, `[Unreleased]` → «Добавлено»: флаг «Показывать
  цену» и стоимость всей группы на карточке группового занятия.

## Workflow follow-up

- Архив change'а — после ревью (`openspec archive add-calendar-show-price`).
