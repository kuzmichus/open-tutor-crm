# AGENTS.md — правила разработки open-tutor-crm

Этот файл — свод правил для работы с кодовой базой (и для AI-ассистентов, и для людей).
Соблюдай их при любом изменении проекта.

## Технологии

Python 3.14 · FastAPI · Uvicorn · SQLAlchemy 2.0 · Alembic · SQLite · Jinja2 · HTMX · Alpine.js · pytest.
Все команды выполняются через менеджер окружений **uv** (см. README.md).
Фронтенд собирается **без сборщиков**: нативный CSS (`@layer` + nesting) и локальные
вендорные скрипты в `app/static/`.

## Структура проекта

Приложение разбито на **доменные модули** и **общий** модуль:

```
main.py                     # точка входа: create_app(), include_router, 404, /static
app/
├── config.py               # настройки (Settings, pydantic-settings)
├── database.py             # engine, SessionLocal, Base, init_db, get_db, PRAGMA foreign_keys
├── models.py               # АГРЕГАТОР моделей (только импорты, ни одного класса)
├── templating.py           # общий Jinja2Templates + TEMPLATE_DIRS + хелперы шаблонов
├── templates/              # ОБЩИЕ шаблоны: base.html, 404.html, auth.html,
│                           # sidebar.html, _logo.html, _person_picker.html
├── static/                 # ОБЩИЕ статические ассеты (см. «Статика и CSS»)
├── common/                 # общие фичи, не привязанные к домену
│   ├── access.py           # require_tutor_id, LoginRequired, LOGIN_URL
│   ├── colors.py           # PALETTE, DEFAULT_TARGET_COLOR, assign_color
│   ├── services/timezones.py
│   └── views/              # health, index (/ → /tutor/), clock (/time), not_found
├── tutor/                  # аккаунт репетитора: регистрация, вход, сессии, сброс пароля
├── student/                # ученики и переиспользуемые контакты
├── group/                  # группы и состав групп
├── lesson/                 # уроки и серии уроков
├── homework/               # домашние задания урока (вкладка урока)
└── calendar/               # недельный календарь (моделей нет — только views/services)
alembic/                    # миграции БД
openspec/                   # спецификации (specs/) и активные change'и (changes/)
tests/                      # pytest-тесты
```

Внутри доменного модуля:

```
app/<module>/
├── models/<имя>.py         # по одному классу на файл
├── services/<имя>.py       # бизнес-логика, выборки, формы, представление
├── views/<имя>.py          # по одному эндпоинту на файл, создаёт router
├── views/__init__.py       # сборка роутера модуля
└── templates/<module>/     # шаблоны модуля (неймспейс подкаталогом)
```

## Правила

1. **Один класс — один файл.** Каждый класс (модель, сервис и т.д.) живёт в своём файле.
2. **Модели** — в `<модуль>/models/<имя_модели>.py`, по одному классу на файл.
   Пример: `app/tutor/models/tutor.py` содержит `class Tutor`.
3. **Views (роуты)** — в `<модуль>/views/<имя_вью>.py`, по одному эндпоинту на файл.
   Пример: `app/lesson/views/move.py`. Каждый файл создаёт `router = APIRouter()`
   (без `prefix=` — полный путь пишется в декораторе). Роутеры собираются
   в `<модуль>/views/__init__.py` и подключаются в `main.py`.
4. **Сервисы** — в `<модуль>/services/<имя>.py`, по одному сервису на файл
   (выборки, запись, разбор формы, представление). Сервис **не знает про FastAPI**:
   на вход — `Session` и очищенные значения, на выход — данные или список ошибок.
   Исключения — `access.py` (там живут `HTTPException`/404) и `page_context.py`.
5. **Шаблоны.** Общие — в `app/templates/`, шаблоны модуля — в `app/<модуль>/templates/`.
   Шаблон модуля неймспейсится подкаталогом (`student/index.html`, `lesson/_form.html`),
   чтобы не было коллизий имён. Все страницы наследуют `base.html` и заполняют
   блоки `title`, `head` (страничные скрипты) и `body`. Партиалы htmx начинаются с `_`.
6. **Общий код**, который нельзя отнести к конкретному домену (health, доступ по сессии,
   палитра цветов, часовые пояса, базовые страницы), — в `app/common/`.
7. **`app/models.py`** — только агрегатор: импортирует модели всех модулей, чтобы они
   зарегистрировались на `Base.metadata`. Там не должно быть ни одного класса.
8. **Статика** (JS/CSS/иконки) кладётся в `app/static/` и отдаётся локально через
   `app.mount("/static", ...)` в `main.py` — **без CDN и без SRI-хешей** в шаблонах
   (иначе несовпадение хеша молча блокирует скрипт).
9. **Связи — только FK-колонки, без `relationship()`.** Связанные строки подгружаются
   одним запросом с `join` и группировкой в сервисе (без N+1 на карточку).
10. **Закрытые списки значений** (статусы, типы, длительности) объявляются кортежем-константой
    в файле модели (`LESSON_TYPES`, `HOMEWORK_STATUSES`, …) — один источник истины
    для `CheckConstraint` в БД, для `options` селекта и для словаря подписей.
11. **Время** хранится в UTC (`DateTime(timezone=True)`, `datetime.now(UTC)`). SQLite теряет
    tzinfo, поэтому значения из БД нормализуются через `app/tutor/services/clock.py`
    (`utcnow`, `as_utc`) перед сравнением.

## Доступ и изоляция данных

- `tutor_id` берётся **только из сессии** — через `require_tutor_id` из `app/common/access.py`.
  Никогда из формы, query-параметра или тела запроса.
- Нет сессии → `LoginRequired` (303 на `/tutor/login`), запрос прерывается до рендера.
- Одна запись проверяется доменным хелпером `get_owned_<entity>(db, id, tutor_id)`:
  `id` и `tutor_id` в одном `SELECT`. **Чужая запись и несуществующая неразличимы — 404**,
  не 403: существование чужой записи не раскрывается.
- Владелец урока выводится из цели (ученик или группа), отдельной колонки `tutor_id`
  у `lessons` нет — выборка идёт через JOIN (`app/lesson/services/access.py`).
- Модули **ри-экспортируют** общий доступ из своего `services/access.py`
  (`from app.common.access import ...`), чтобы вьюхи не зависели от `common` напрямую
  и новый модуль не тянул зависимость на чужой домен.

## Веб-слой: HTMX + Alpine

- Страница целиком — обычный GET-роут с `TemplateResponse(request, "…/index.html", ctx)`.
- Частичное обновление — отдельный роут-партиал (`/tutor/students/list`,
  `/tutor/groups/list`, `/tutor/lessons/list`) и `hx-target`/`hx-swap="innerHTML"`.
- Сохранение формы → пустой ответ + `HX-Trigger` (`student-saved`, `group-saved`,
  `group-deleted`, `lesson-saved`). Слушатель на странице (`hx-trigger="… from:body"`)
  перезапрашивает свой контейнер — DOM обновляется с сервера, а не руками в JS.
- Модалки живут в контейнере `#modal`: `hx-get` открывает форму, ответ — фрагмент.
  Форма ДЗ возвращает **свою панель** (`outerHTML`), а не пустое тело.
- Без `HX-Request` POST отвечает 303-редиректом на страницу — форма работает и без JS.
- Клиентское состояние — Alpine-фабрики в `app/static/*.js` (`students.js`, `groups.js`,
  `lessons.js`, `calendar.js`, `picker.js`, `combobox.js`). Скрипты подключаются
  **до** `alpine.min.js` (подписка на `alpine:init` должна случиться раньше обхода DOM)
  и точечно — через `{% block head %}` конкретной страницы.
- Серверные подписи и форматирование — в `<модуль>/services/presentation.py`
  (чистые функции без БД и HTTP), регистрируются в `app/templating.py`
  через `register_template_helpers()`. Шаблон не форматирует бизнес-данные сам.

## Статика и CSS

- `app/static/styles.css` — дизайн-система: секции `tokens → base → components → utilities`,
  нативный `@layer` + nesting. Цвета только через токены (`var(--brand)`), не литералами.
- **Нативный CSS не умеет конкатенацию селекторов через `&`**: запись `&__el` / `&--mod`
  синтаксически валидна, но браузер выбрасывает правило целиком. Пишите плоские
  BEM-селекторы (`.group-card__menu`).
- Каждый литеральный BEM-класс из шаблонов модулей должен быть описан в `styles.css` —
  это проверяют тесты `tests/test_css_styles.py`.
- `app/static/dist/app.css` — мёртвый Tailwind-артефакт, на него **никто не ссылается**.
  Не подключайте его и не переносите оттуда правила.
- Вендорные файлы (`htmx.min.js`, `alpine.min.js`, `lucide.min.js`) коммитятся как есть.

## База данных и миграции

- Схема меняется **только** миграцией Alembic (autogenerate), не руками.
  `init_db()` в `lifespan` — удобство локальной разработки, не замена миграциям.
- SQLite не проверяет FK по умолчанию: `app/database.py` включает `PRAGMA foreign_keys=ON`
  слушателем на `Engine.connect`. Удаление родителя каскадится (`ondelete="CASCADE"`).
- Инварианты держатся и в БД (`CheckConstraint`, `UNIQUE`), и в валидации формы:
  модель не должна принимать значение, которого нет в закрытом списке.
- Строковые id — `String(36)` + `uuid4`; репетитор — владелец корневых сущностей.

## Тесты

- `tests/conftest.py` подменяет `DATABASE_URL` на `sqlite:///:memory:` **до импорта приложения**;
  база пересоздаётся на каждый тест (`Base.metadata.create_all` / `drop_all`).
- Фикстуры: `client` (TestClient), `tutor_factory`, `student_factory`, `group_factory`,
  `group_member_factory`, `contact_factory`. У фабрик уникальные значения по умолчанию —
  их можно звать подряд, а `tutor_id` при необходимости передаётся явно.
- Тест изоляции обязателен для любой новой сущности: чужой репетитор получает 404,
  а не 403 и не пустую страницу.
- Поведение через HTTP проверяется тем же путём, что у пользователя: те же маршруты,
  те же поля формы, разметка ищется по тексту/атрибутам, а не по внутренностям функций.

## Спецификации (OpenSpec)

- `openspec/specs/<capability>/spec.md` — принятые требования (сценарии WHEN/THEN).
- `openspec/changes/<change>/` — активный change: `proposal.md`, `design.md`, `tasks.md`,
  `specs/<capability>/spec.md`. Завершённые уезжают в `openspec/changes/archive/`.
- Новая фича или заметное изменение поведения начинается с change'а: сначала
  планирование (`proposal` / `design` / `tasks`), потом код по задачам.
- Работающий в проекте набор команд — в `.opencode/commands/` (`opsx-propose`,
  `opsx-apply`, `opsx-update`, `opsx-archive`, `opsx-sync`, `opsx-explore`).

## Как добавить новый доменный модуль

1. Создай каталог `app/<module>/` с `__init__.py`, `models/`, `services/`, `views/`, `templates/`.
2. Добавь модель в `app/<module>/models/<name>.py` (один класс — один файл)
   и `from app.<module>.models.<name> import <Name>  # noqa: F401` в `app/models.py`.
3. Добавь сервисы в `app/<module>/services/`; общий доступ к одной записи оформи как
   `access.py` с `get_owned_<entity>` (ри-экспорт `require_tutor_id` из `app.common.access`).
4. Добавь view в `app/<module>/views/<name>.py` (создаёт `router`) и собери
   роутеры модуля в `app/<module>/views/__init__.py`. **Статические маршруты
   (`/list`, `/new`, `/lookup/...`) регистрируй до маршрутов с `/{id}`** —
   иначе параметрический путь перехватит их.
5. Зарегистрируй каталог шаблонов: допиши `_APP_DIR / "<module>" / "templates"`
   в `TEMPLATE_DIRS` (`app/templating.py`), а хелперы отображения — через
   `register_template_helpers()` из `<module>/services/presentation.py`.
6. Подключи роутер модуля в `main.py` (`app.include_router(...)`).
7. Создай миграцию: `uv run alembic revision --autogenerate -m "add <module>"`
   и примени её `uv run alembic upgrade head`.
8. Напиши тесты в `tests/` (поведение, изоляция по репетитору, партиалы htmx).

## Команды

```bash
uv sync                                   # установить зависимости
uv run pytest                             # прогнать тесты
uv run pytest -q tests/test_lesson_create.py   # один файл
uv run alembic upgrade head               # применить миграции
uv run alembic revision --autogenerate -m "..."   # новая миграция
uv run alembic heads                      # текущая голова схемы
uv run uvicorn main:app --host 0.0.0.0 --port 8000  # запуск сервера
```

## Требования к изменениям

- Тесты в `tests/` должны оставаться зелёными (`uv run pytest`).
- Новый домен/поведение — с тестами, включая изоляцию по репетитору.
- Миграции создаются через autogenerate и применяются штатно (`alembic upgrade head`).
- Новый BEM-класс в шаблоне — с правилом в `app/static/styles.css`.
- Модули и функции сопровождаются docstring'ами на русском; комментарии объясняют
  **почему** так сделано (инвариант, ловушка, решение), а не пересказывают код.
- Перед PR обнови затронутые спецификации в `openspec/` и, если меняется
  поведение для пользователя, — README.md.
