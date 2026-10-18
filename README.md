# open-tutor-crm

Открытая CRM для репетиторов.

Технологический каркас: **Python 3.14**, **FastAPI** + **Uvicorn**,
**SQLAlchemy 2.0**, **Alembic**, **SQLite**, **Jinja2**, **HTMX**, тесты на **pytest**.
Все команды выполняются через менеджер окружений **uv**.

Подробнее о структуре и правилах разработки — в [AGENTS.md](AGENTS.md).

## Структура

```
main.py               # точка входа: uv run uvicorn main:app
app/
├── config.py         # настройки (Settings, поддержка .env)
├── database.py       # engine, SessionLocal, Base, init_db, get_db
├── models.py         # агрегатор моделей (только импорты)
├── templating.py     # общий Jinja2Templates (все каталоги шаблонов)
├── templates/        # общие шаблоны (base.html, index.html)
├── common/           # health-check, главная, htmx-часы
├── tutor/            # модуль «Репетитор»: models/, views/, templates/
└── student/          # модуль «Ученик»: models/, views/, templates/
alembic/              # миграции БД
tests/                # pytest-тесты
```

## Требования

- [uv](https://docs.astral.sh/uv/) (менеджер окружений и зависимостей)
- Python 3.14 — uv подтянет автоматически (см. `requires-python` в `pyproject.toml`)

## Установка и запуск (локально)

```bash
# 1. Клонировать репозиторий и перейти в каталог
git clone git@github.com:kuzmichus/open-tutor-crm.git && cd open-tutor-crm

# 2. Создать виртуальное окружение и установить зависимости
uv sync

# 3. Применить миграции БД (создаст SQLite-файл tutor.db)
uv run alembic upgrade head

# 4. Запустить сервер (development)
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

После запуска:

- `GET http://localhost:8000/health` → `200` + `{"status": "ok"}`
- `GET http://localhost:8000/` → страница «Hello world» с часами,
  обновляемыми каждую секунду через htmx (`GET /time`)
- `GET http://localhost:8000/tutor/register` → регистрация репетитора
- `GET http://localhost:8000/tutor/login` → вход
- `GET http://localhost:8000/tutor/` → личный кабинет (только после входа)
- `GET http://localhost:8000/tutor/remember-password` → восстановление пароля
- `GET http://localhost:8000/tutor/students` → список учеников (только после входа)
- `GET http://localhost:8000/tutor/students/{id}` → карточка ученика
- Swagger UI: `http://localhost:8000/docs`

> Для локальной разработки таблицы создаются автоматически при старте
> (`init_db` в lifespan). Для воспроизводимых схем используйте Alembic
> (`uv run alembic upgrade head`).

## Ученики

Ученик принадлежит репетитору: все маршруты модуля лежат под префиксом
личного кабинета `/tutor/students/`, требуют действующей сессии,
а выборка всегда ограничена `tutor_id` вошедшего репетитора. Чужой ученик
неотличим от несуществующего — ответ `404`.

### Маршруты

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/tutor/students` | список карточек, поиск и фильтр по статусу |
| `GET` | `/tutor/students/list` | партиал сетки для htmx (поиск без перезагрузки) |
| `GET` | `/tutor/students/new` | форма создания в модальном окне |
| `POST` | `/tutor/students` | создание ученика |
| `GET` | `/tutor/students/{id}` | карточка ученика |
| `GET` | `/tutor/students/{id}/edit` | форма редактирования в модальном окне |
| `POST` | `/tutor/students/{id}` | сохранение полей, контактов, плательщика и напоминаний |
| `POST` | `/tutor/students/{id}/archive` | в архив / возврат из архива одним действием |
| `GET` | `/tutor/students/contacts/lookup` | подсказка существующего контакта при вводе |

### Схема: три таблицы

```
tutors 1 --- N students            students.tutor_id       NOT NULL, ON DELETE CASCADE
tutors 1 --- N contacts            contacts.tutor_id       NOT NULL
students N --- N contacts          через student_contacts (роль + напоминания)
students.payer_contact_id  -->  contacts.id                 NULL = платит сам ученик
```

- `students` — карточка: имя и фамилия, телефон, email, признак
  ребёнок/взрослый, класс (1–11), школа, уровень, заметки, статус, часовой
  пояс и три флага напоминаний. Телефон и email необязательны и **не**
  уникальны.
- `contacts` — переиспользуемые взрослые: ФИО, телефон, email, часовой пояс.
  Один контакт привязывается к нескольким ученикам без копирования.
- `student_contacts` — привязка с ролью (`мама`, `бабушка`, `водитель` —
  свободный текст) и тремя настройками напоминаний, отдельными для каждой
  пары «ученик — контакт».

Напоминания хранятся и у ученика, и у привязки контакта: получателем может
быть и сам взрослый ученик без контактов, и родитель конкретного ребёнка.

### Архивирование вместо удаления

Ученика нельзя удалить — только перевести в архив. Архивированный ученик
не показывается в списке по умолчанию, но доступен под фильтром «В архиве»,
сохраняет все поля и контакты и возвращается из архива тем же действием
(«Вернуть из архива»).

### Фронтенд-ассеты

Все скрипты лежат в `app/static/` и отдаются локально — без CDN:

| Файл | Назначение |
|---|---|
| `htmx.min.js` | обновление фрагментов без перезагрузки (список, модалка) |
| `alpine.min.js` | клиентское состояние: модалка, сегмент «ребёнок/взрослый», вид списка |
| `students.js` | фабрики `Alpine.data` для страниц учеников (подключается до Alpine) |
| `lucide.min.js` | иконки |
| `app.js` | сайдбар, тема, инициализация иконок |

## Тесты

```bash
uv run pytest            # все тесты
uv run pytest -q         # кратко
uv run pytest tests/test_models.py   # конкретный файл
```

## Миграции (Alembic)

```bash
uv run alembic upgrade head                        # применить все миграции
uv run alembic revision --autogenerate -m "..."    # сгенерировать новую миграцию
uv run alembic current                             # текущая ревизия
uv run alembic downgrade -1                        # откатить одну ревизию
```

## Конфигурация

Параметры переопределяются через переменные окружения или файл `.env`
(корень проекта). Пример `.env`:

```env
DATABASE_URL=sqlite:///./tutor.db
APP_NAME=Open Tutor CRM
```

| Переменная     | По умолчанию           | Описание              |
|----------------|------------------------|-----------------------|
| `DATABASE_URL` | `sqlite:///./tutor.db` | URL базы данных       |
| `APP_NAME`     | `Open Tutor CRM`       | Название приложения   |

## Развёртывание (production)

### Вариант A. systemd + Uvicorn

Собрать артефакты и развернуть как сервис:

```bash
uv sync --no-dev                 # зависимости без dev-группы
uv run alembic upgrade head      # применить миграции перед стартом
```

Юнит `/etc/systemd/system/open-tutor-crm.service`:

```ini
[Unit]
Description=Open Tutor CRM
After=network.target

[Service]
Type=exec
User=www-data
WorkingDirectory=/opt/open-tutor-crm
ExecStart=/opt/open-tutor-crm/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=on-failure
Environment=DATABASE_URL=sqlite:////opt/open-tutor-crm/tutor.db
Environment=APP_NAME=Open Tutor CRM

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now open-tutor-crm
sudo systemctl status open-tutor-crm
```

За обратным прокси (nginx/caddy) обычно поднимают `127.0.0.1:8000`
и отдают статику/проксируют на него. Для боевого SQLite — вынесите
`DATABASE_URL` на постоянный диск/том.

### Вариант B. Docker

`Dockerfile`:

```dockerfile
FROM python:3.14-slim

# uv — менеджер зависимостей
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY . .
RUN uv sync --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

```bash
docker build -t open-tutor-crm .
docker run --rm -p 8000:8000 -e DATABASE_URL=sqlite:////data/tutor.db open-tutor-crm
```

> Для продакшена предпочтительнее внешняя БД (PostgreSQL) — достаточно
> поменять `DATABASE_URL` и зависимости; SQLAlchemy и Alembic работают с ней без изменений кода моделей.
