# AGENTS.md — правила разработки open-tutor-crm

Этот файл — свод правил для работы с кодовой базой: и для людей, и для
AI-ассистентов. Соблюдай их при любом изменении проекта.

- **README.md** — установка, эксплуатация, переменные окружения, интеграции.
- **openspec/specs/** — принятое поведение (сценарии WHEN/THEN).
- **openspec/changes/** — активные изменения; завершённые уезжают в `archive/`.

Документация, docstring'и и комментарии в проекте — на русском.

## Технологии

Python 3.14 · FastAPI · Uvicorn · SQLAlchemy 2.0 · Alembic · SQLite (по
умолчанию) / PostgreSQL · Jinja2 · HTMX · Alpine.js · pytest.

Все команды выполняются через менеджер окружений **uv** (см. README.md).
Фронтенд собирается **без сборщиков и без Node.js**: нативный CSS
(`@layer` + nesting) и локальные вендорные скрипты в `app/static/`.

## Команды

```bash
uv sync                                            # зависимости (включая dev)
uv run uvicorn main:app --reload                   # dev-сервер на :8000
uv run pytest -n auto                              # все тесты
uv run pytest -q tests/test_lesson_create.py       # один файл
uv run alembic upgrade head                        # применить миграции
uv run alembic revision --autogenerate -m "..."    # новая миграция
uv run alembic check                               # модели == схема?
uv lock --check                                    # uv.lock == pyproject.toml?
uv run python scripts/build_icons.py               # пересобрать набор иконок
uv run python scripts/seed_demo.py                 # демо-данные (разрушающе)
uv run python scripts/smoke_demo.py                # проверить рендер страниц
uv run --with pillow python scripts/build_favicons.py  # пересобрать favicon
uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py
```

Схему БД создаёт **только Alembic**. Перед первым запуском dev-сервера
выполните `uv run alembic upgrade head`, иначе приложение упадёт на первом
запросе с «no such table».

## Структура проекта

Приложение разбито на **доменные модули** и **общий** модуль:

```
main.py                     # create_app(): include_router, 404, /static
cron.py                     # точка входа внешнего планировщика (раз в минуту)
app/
├── config.py               # Settings (pydantic-settings), валидация конфигурации
├── database.py             # engine, SessionLocal, Base, get_db, PRAGMA foreign_keys
├── models.py               # АГРЕГАТОР моделей (только импорты, ни одного класса)
├── templating.py           # общий Jinja2Templates, TEMPLATE_DIRS, хелперы шаблонов
├── templates/              # ОБЩИЕ шаблоны: base.html, 404.html, auth.html, sidebar
├── static/                 # ОБЩИЕ ассеты: styles.css, JS, шрифты, иконки, favicons
├── common/                 # общие фичи, не привязанные к домену
│   ├── access.py           # require_tutor_id, LoginRequired, get_owned_entity
│   ├── colors.py           # PALETTE, DEFAULT_TARGET_COLOR, assign_color
│   ├── constraints.py      # sql_string_in / sql_int_in для CHECK-ограничений
│   ├── responses.py        # is_htmx, saved_response, dialog_closed
│   ├── services/           # forms, timezones, tutor_time, cron
│   └── views/              # health, index (/), clock, favicon, auth-status, 404
├── tutor/                  # аккаунт: регистрация, вход, сессии, профиль, настройки,
│                           # сброс пароля, часовой пояс, параметры (tutor_params)
├── student/                # ученики и переиспользуемые контакты взрослых
├── group/                  # группы и состав групп
├── lesson/                 # уроки и серии уроков
├── homework/               # домашние задания урока
├── calendar/               # недельная сетка (views/services, моделей нет)
├── unavailability/         # отпуска, больничные, выходные
├── slot/                   # окна для записи
├── booking/                # брони и публичная запись /s/<tutor_id>
├── finance/                # счёт ученика, платежи, возвраты, расходы,
│                           # аналитика, прогноз, НПД, счёт за период
├── stats/                  # статистика загрузки, удержания, конверсии
├── task/                   # задачи: канбан по этапам и список по срокам
├── mailing/                # рассылки, шаблоны, журнал сообщений
├── messenger/              # Telegram и MAX: отправка, сводки, приглашения
├── mail/                   # SMTP-транспорт (только services)
├── gcalendar/              # Google Календарь: OAuth, синхронизация, сверка
├── files/                  # файлы ДЗ: local/S3, загрузка, скачивание, доступ
├── cabinet/                # кабинеты ученика (/student) и родителя (/parent)
└── landing/                # лендинг: редактор, публикация, картинки
alembic/                    # миграции БД
openspec/                   # спецификации (specs/) и активные change'и (changes/)
scripts/                    # seed_demo, smoke_demo, build_icons, build_favicons, vendor/
tests/                      # pytest-тесты
landing/                    # данные лендинга на диске (LANDING_ROOT, в .gitignore)
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

Не у каждого модуля есть все слои: `calendar` и `stats` живут без моделей,
`mail`, `gcalendar` и `messenger` — без собственных вьюх (их настройки
встроены в профиль репетитора), `landing` хранит данные на диске, а не в БД.

## Правила

1. **Один класс — один файл.** Каждый класс (модель, сервис и т.д.) живёт в своём файле.
2. **Модели** — в `<модуль>/models/<имя_модели>.py`, по одному классу на файл.
   Пример: `app/tutor/models/tutor.py` содержит `class Tutor`.
3. **Views (роуты)** — в `<модуль>/views/<имя_вью>.py`, по одному эндпоинту на файл.
   Пример: `app/lesson/views/move.py`. Каждый файл создаёт `router = APIRouter()`
   (без `prefix=` — полный путь пишется в декораторе). Роутеры собираются
   в `<модуль>/views/__init__.py` и подключаются в `main.py`.
   **Статические маршруты (`/list`, `/new`, `/lookup/...`) регистрируй до
   маршрутов с `/{id}`** — иначе параметрический путь перехватит их.
4. **Сервисы** — в `<модуль>/services/<имя>.py`, по одному сервису на файл
   (выборки, запись, разбор формы, представление). Сервис **не знает про FastAPI**:
   на вход — `Session` и очищенные значения, на выход — данные или список ошибок.
   Исключения — `access.py` (там живут `HTTPException`/404), `page_context.py`
   и сервисы, которые по смыслу сводят несколько сессий к одному правилу доступа
   (`app/files/services/access.py`).
5. **Шаблоны.** Общие — в `app/templates/`, шаблоны модуля — в `app/<модуль>/templates/`.
   Шаблон модуля неймспейсится подкаталогом (`student/index.html`, `lesson/_form.html`),
   чтобы не было коллизий имён. Все страницы наследуют `base.html` и заполняют
   блоки `title`, `head` (страничные скрипты) и `body`. Партиалы htmx начинаются с `_`.
6. **Общий код**, который нельзя отнести к конкретному домену (health, доступ по сессии,
   палитра цветов, часовые пояса, разбор форм, базовые страницы), — в `app/common/`.
7. **`app/models.py`** — только агрегатор: импортирует модели всех модулей, чтобы они
   зарегистрировались на `Base.metadata`. Там не должно быть ни одного класса.
8. **Статика** (JS/CSS/иконки/шрифты) кладётся в `app/static/` и отдаётся локально через
   `app.mount("/static", ...)` в `main.py` — **без CDN и без SRI-хешей** в шаблонах
   (иначе несовпадение хеша молча блокирует скрипт).
9. **Связи — только FK-колонки, без `relationship()`.** Связанные строки подгружаются
   одним запросом с `join` и группировкой в сервисе (без N+1 на карточку).
10. **Закрытые списки значений** (статусы, типы, длительности, категории) объявляются
    кортежем-константой в файле модели (`LESSON_TYPES`, `HOMEWORK_STATUSES`, …) —
    один источник истины для `CheckConstraint` в БД, для `options` селекта и для
    словаря подписей.
11. **Время** хранится в UTC (`DateTime(timezone=True)`, `datetime.now(UTC)`). SQLite
    теряет tzinfo, поэтому значения из БД нормализуются через
    `app/tutor/services/clock.py` (`utcnow`, `as_utc`) перед сравнением.

## Доступ и изоляция данных

- `tutor_id` берётся **только из сессии** — через `require_tutor_id` из
  `app/common/access.py`. Никогда из формы, query-параметра или тела запроса.
- Нет сессии → `LoginRequired` (303 на `/tutor/login`), запрос прерывается до рендера.
- Одна запись проверяется доменным хелпером `get_owned_<entity>(db, id, tutor_id)`:
  `id` и `tutor_id` в одном `SELECT`. **Чужая запись и несуществующая неразличимы —
  404**, не 403: существование чужой записи не раскрывается. Простые случаи (своя
  колонка `tutor_id`) делегируют общему `get_owned_entity` из `app/common/access.py`;
  владелец через JOIN (урок, бронь, операция счёта) — своя выборка в доменном
  `services/access.py`.
- Владелец урока выводится из цели (ученик или группа), отдельной колонки `tutor_id`
  у `lessons` нет — выборка идёт через JOIN (`app/lesson/services/access.py`).
- Модули **ри-экспортируют** общий доступ из своего `services/access.py`
  (`from app.common.access import ...`), чтобы вьюхи не зависели от `common` напрямую
  и новый модуль не тянул зависимость на чужой домен.
- Публичные поверхности ограничены и не раскрывают чужие данные: запись `/s/<tutor_id>`,
  кабинеты `/student` и `/parent` (три независимые сессии), `/landing-assets/...`,
  `GET /files/{id}` (доступ проверяется для репетитора, ученика и родителя).
- Файл ДЗ доступен владельцу, ученику урока (включая участника группы) и родителю
  ребёнка; остальным — 404. Имя файла в хранилище генерирует сервер, исходное имя
  живёт только в метаданных.
- Секреты (токены ботов, OAuth, SMTP, S3) — только в окружении или `tutor_params`,
  никогда в шаблонах и не в git.

## Веб-слой: HTMX + Alpine

- Страница целиком — обычный GET-роут с `TemplateResponse(request, "…/index.html", ctx)`.
- Частичное обновление — отдельный роут-партиал (`/tutor/students/list`,
  `/tutor/groups/list`, `/tutor/lessons/list`) и `hx-target`/`hx-swap="innerHTML"`.
- Сохранение формы → `saved_response()`: пустой ответ + `HX-Trigger`
  (`student-saved`, `group-saved`, `lesson-saved`, …). Слушатель на странице
  (`hx-trigger="… from:body"`) перезапрашивает свой контейнер — DOM обновляется
  с сервера, а не руками в JS.
- Модалки живут в контейнере `#modal`: `hx-get` открывает форму, ответ — фрагмент.
  Закрытие диалога — `dialog_closed()` (`HX-Trigger` + `HX-Reswap: none`), а не
  пустое тело с `outerHTML` (иначе `htmx:swapError`).
- Без `HX-Request` POST отвечает 303-редиректом на страницу — форма работает и без JS.
- Клиентское состояние — Alpine-фабрики в `app/static/*.js` (`students.js`, `groups.js`,
  `lessons.js`, `calendar.js`, `tasks.js`, `picker.js`, `combobox.js`, …). Скрипты
  подключаются **до** `alpine.min.js` (подписка на `alpine:init` должна случиться
  раньше обхода DOM) и точечно — через `{% block head %}` конкретной страницы.
- Серверные подписи и форматирование — в `<модуль>/services/presentation.py`
  (чистые функции без БД и HTTP), регистрируются в `app/templating.py`
  через `register_template_helpers()`. Шаблон не форматирует бизнес-данные сам.

## Статика и CSS

- `app/static/styles.css` — дизайн-система: секции `tokens → base → components →
  utilities`, нативный `@layer` + nesting. Цвета только через токены
  (`var(--brand)`), не литералами.
- **Нативный CSS не умеет конкатенацию селекторов через `&`**: запись `&__el` /
  `&--mod` синтаксически валидна, но браузер выбрасывает правило целиком. Пишите
  плоские BEM-селекторы (`.group-card__menu`).
- Каждый литеральный BEM-класс из шаблонов модулей должен быть описан в
  `styles.css` — это проверяют тесты `tests/test_css_styles.py`.
- Шрифты лежат локально в `app/static/fonts/` (`@font-face` в `styles.css`),
  без Google Fonts и других CDN.
- Вендорные файлы (`htmx.min.js`, `alpine.min.js`, GrapesJS в
  `app/static/dist/grapesjs/`) коммитятся как есть.
- **Иконки — не полный Lucide, а собранный набор** `app/static/icons.js`.
  Полный бандл лежит в `scripts/vendor/lucide.min.js` как источник данных и
  браузеру не отдаётся. Добавили иконку в разметку или в Python — пересоберите
  набор: `uv run python scripts/build_icons.py`. Свежесть, полноту и вес
  проверяет `tests/test_icons_bundle.py`.
- Favicon-набор в `app/static/favicons/` собирается из
  `scripts/vendor/favicon-source.png` скриптом `scripts/build_favicons.py`.
- `app/static/dist/app.css` — мёртвый локальный Tailwind-артефакт: на него
  никто не ссылается. Не подключайте его и не переносите оттуда правила.
- Лендинг публикуется **без** общего `app.css`: его страница — самостоятельный
  HTML-документ со своими стилями (см. `app/landing/services/template.py`).

## Время, деньги и идентификаторы

- **Время.** Ввод формы трактуется как настенное время в зоне педагога и
  переводится в UTC через `app/common/services/tutor_time.py` (`to_utc`);
  показ и границы операций считаются в зоне педагога, и только результат
  переводится в UTC. Нельзя прибавлять `timedelta` к UTC-значению: при
  переходе на летнее время это сдвигает дни.
- **Деньги.** Суммы в счёте, ценах уроков и группах — целые рубли (`Integer`),
  без копеек. Ставки, коэффициенты и проценты — `Numeric`/`Decimal`, не `float`.
  Форматирование — только через `money()`/`signed_money()` из
  `finance/services/presentation.py`.
- **Идентификаторы.** Строковые id — `String(36)` + `uuid4`; репетитор —
  владелец корневых сущностей.
- **Закрытые списки** — правило 10. Значение вне списка не должно приниматься
  ни формой, ни БД (`CheckConstraint`).

## База данных и миграции

- Схема меняется **только** миграцией Alembic (autogenerate), не руками.
- SQLite не проверяет FK по умолчанию: `app/database.py` включает
  `PRAGMA foreign_keys=ON` слушателем на `Engine.connect`. Удаление родителя
  каскадируется (`ondelete="CASCADE"`).
- Инварианты держатся и в БД (`CheckConstraint`, `UNIQUE`, частичные индексы),
  и в валидации формы: модель не должна принимать значение, которого нет
  в закрытом списке.
- `alembic check` сравнивает модели со схемой. Правка модели без миграции —
  красный PR. Новый домен или поле — всегда с autogenerate-миграцией.
- Миграция перевода старых дат в UTC читает `MIGRATION_SOURCE_TZ`; трогать её
  без необходимости не нужно.

## Внешние интеграции и cron

- **Конфигурация проверяется на старте.** Неполная настройка S3
  (`FILES_BACKEND=s3`) или SMTP (`SMTP_HOST`) — ошибка запуска с именами
  недостающих переменных, а не падение на первом запросе пользователя.
  Настройки читаются при старте: после смены переменных нужен перезапуск.
- **Google Календарь.** Домен уроков про Google не знает: вьюха сохраняет урок
  своей транзакцией, затем зовёт `sync_lesson`/`delete_lesson_event`. Ошибка
  Google не ломает действие пользователя — урок уже сохранён, ошибка уходит
  в лог (`gcalendar`) и в карточку интеграции. Синхронизация односторонняя,
  cron-задание `gcalendar.reconcile` догоняет пропущенное.
- **Почта.** `SMTP_HOST` пуст — почта выключена; ссылка восстановления пароля
  не показывается на странице, а пишется в лог (`WARNING` логгера `mail`).
  Транспорт один на всё приложение — `app/mail/services/sender.py`.
- **Мессенджеры.** Отправка возвращает список ошибок (пустой — доставлено),
  токены хранятся в `tutor_params`. Обёртки `LoggingSender(RetrySender(...))`
  добавляют журнал и повтор.
- **Файлы.** Бэкенд (`local`/`s3`) запоминается у каждого файла: после смены
  `FILES_BACKEND` старые файлы продолжают скачиваться из прежнего хранилища.
  Локальный каталог (`FILES_LOCAL_ROOT`) — такие же данные, как база: копируйте
  его вместе с `tutor.db`.
- **Лендинг.** Работает только в `SINGLE_MODE=true`, хранится на диске в
  `LANDING_ROOT` (не в БД и не в `FILES_*`). Запись атомарная (временный файл +
  `os.replace`), имя ассета генерирует сервер, в путь попадает только расширение
  из allowlist. В редактируемом теле скрипты не сохраняются — тег
  `/static/landing-auth.js` возвращается сервером.
- **Cron.** Задания регистрируются в `TASKS` (`app/common/services/cron.py`),
  логика живёт в доменных сервисах. Каждое задание — своя транзакция; коммит
  делает runner, а не сервис. Задания обязаны быть идемпотентными.

## Тесты

- `tests/conftest.py` подменяет `DATABASE_URL` на `sqlite:///:memory:` **до импорта
  приложения**; база пересоздаётся на каждый тест (`Base.metadata.create_all` /
  `drop_all`).
- Прогон герметичен к окружению: conftest **до импорта приложения** нейтрализует
  «утекающие» переменные (`SINGLE_MODE`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `LANDING_ROOT`), иначе `.env` и данные живого workspace (например, опубликованный
  лендинг) меняют результат тестов. Новое поле настроек, читаемое из `.env`, —
  добавь его нейтрализацию в conftest; тест «дефолтного» значения поля снимает
  переменную через `monkeypatch.delenv`, потому что `Settings(_env_file=None)`
  читает реальное окружение.
- Фикстуры: `client` (TestClient), `tutor_factory`, `student_factory`,
  `group_factory`, `group_member_factory`, `contact_factory`,
  `unavailability_factory`, `lesson_factory`, `operation_factory`,
  `slot_factory`, `booking_factory`, `expect_integrity_error`.
  У фабрик уникальные значения по умолчанию — их можно звать подряд.
- Тест изоляции обязателен для любой новой сущности: чужой репетитор получает
  404, а не 403 и не пустую страницу.
- Поведение через HTTP проверяется тем же путём, что у пользователя: те же
  маршруты, те же поля формы, разметка ищется по тексту/атрибутам, а не по
  внутренностям функций.
- Есть тесты «свежести» артефактов: CSS-классы, набор иконок, favicon, версия
  приложения. Если правили шаблон/иконку/версию — пересоберите артефакт, иначе
  тест краснеет.
- Новое поведение — с тестами. `uv run pytest -n auto` должен оставаться зелёным.

## Спецификации (OpenSpec)

- `openspec/specs/<capability>/spec.md` — принятые требования (сценарии WHEN/THEN).
- `openspec/changes/<change>/` — активный change: `proposal.md`, `design.md`,
  `tasks.md`, `specs/<capability>/spec.md`. Завершённые уезжают в
  `openspec/changes/archive/`.
- Новая фича или заметное изменение поведения начинается с change'а: сначала
  планирование (`proposal` / `design` / `tasks`), потом код по задачам.
- Работающий в проекте набор команд — в `.opencode/commands/` (`opsx-propose`,
  `opsx-apply`, `opsx-update`, `opsx-archive`, `opsx-sync`, `opsx-explore`).

## Как добавить новый доменный модуль

1. Создай каталог `app/<module>/` с `__init__.py`, `models/`, `services/`,
   `views/`, `templates/` (только нужные слои).
2. Добавь модель в `app/<module>/models/<name>.py` (один класс — один файл)
   и `from app.<module>.models.<name> import <Name>  # noqa: F401` в `app/models.py`.
3. Добавь сервисы в `app/<module>/services/`; общий доступ к одной записи оформи как
   `access.py` с `get_owned_<entity>` (ри-экспорт `require_tutor_id` из
   `app.common.access`).
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
9. Если появился новый каталог в корне проекта — добавь его в `COPY`
   рантайм-стадии `Dockerfile`: смоук-проверка контейнера ловит забытый путь.
10. Обнови затронутые спецификации в `openspec/` и, если меняется поведение
    для пользователя, — README.md.

## Проверки и релиз (GitHub Actions)

`.github/workflows/ci.yml` — переиспользуемый workflow с триггерами `push`,
`pull_request` и `workflow_call`. Джобы (все — только чтение репозитория):

| Джоба | Команда |
|---|---|
| `tests` | `uv sync --frozen`, `uv run pytest -n auto` |
| `lock` | `uv lock --check` |
| `migrations` | `alembic upgrade head` + `alembic check` на `sqlite:///./ci-check.db` |
| `lint` | `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py` |
| `docker` | сборка образа (`push: false`) и смоук `GET /health` в контейнере |

Правила, которые из этого следуют:

- **Линт узкий намеренно.** Широкий набор ruff сейчас красный, `ruff format`
  затронул бы сотни файлов — это отдельная задача. Версия ruff пинуется
  в workflow, а не в `pyproject.toml`, чтобы не трогать `uv.lock`.
- **`alembic check` — не формальность.** Он сравнивает модели со схемой,
  поэтому правка модели без миграции даёт красный PR.
- **Новый каталог в корне** должен попасть в `COPY` рантайм-стадии `Dockerfile`:
  смоук-проверка контейнера ловит забытый путь.
- **Версия — только в `pyproject.toml`.** `app/__init__.py` и `main.py` читают её
  через `tomllib`, отдельного литерала в коде нет (закреплено
  `tests/test_app_version.py`). `pyproject.toml` копируется в рантайм-образ
  именно ради этого.
- **Публикация только ручная.** `.github/workflows/release.yml` запускается через
  `workflow_dispatch` с обязательным `version`, сверяет её с манифестом, вызывает
  `ci.yml` целиком, публикует `linux/amd64` с четырьмя тегами и последним шагом
  создаёт релиз GitHub. Секреты `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`
  используются только в этом workflow — не переносите их в `ci.yml`.
- **Ночной образ** (`.github/workflows/nightly.yml`) публикует текущий HEAD `main`
  под тегом `night`, только если `ci.yml` зелёный. Это не релиз: git-теги
  и релизы GitHub не создаются, `latest` не двигается.

## Требования к изменениям

- Тесты в `tests/` должны оставаться зелёными (`uv run pytest -n auto`).
- Новый домен/поведение — с тестами, включая изоляцию по репетитору.
- Миграции создаются через autogenerate и применяются штатно (`alembic upgrade head`).
- Изменение модели без миграции, правка `pyproject.toml` без `uv lock` и
  синтаксическая ошибка валят CI — проверяйте локально до push.
- Новый BEM-класс в шаблоне — с правилом в `app/static/styles.css`.
- Новая иконка — с пересборкой `app/static/icons.js`.
- Модули и функции сопровождаются docstring'ами на русском; комментарии объясняют
  **почему** так сделано (инвариант, ловушка, решение), а не пересказывают код.
- Перед PR обнови затронутые спецификации в `openspec/` и, если меняется
  поведение для пользователя, — README.md и CHANGELOG.md.
- Локальные данные (`tutor.db`, `tutor.db.bak-*`, `/files/`, `/landing/`, `.env`)
  не коммитятся — они в `.gitignore`.
