# Open Tutor CRM

**Открытая CRM для репетиторов: ученики, группы, уроки и расписание — на вашем собственном сервере.**

Проект для частных преподавателей, которым нужен порядок в записях, расписании и оплатах,
но не нужны подписки, чужие облака и десятки лишних полей в интерфейсе.
Один репетитор — один аккаунт — только его данные.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)

## Возможности

Open Tutor CRM — веб-приложение, которое закрывает ежедневную рутину репетитора:

- **Ученики** — карточки с контактами, классом, школой, уровнем и заметками; поиск и фильтры по статусу.
- **Контакты** — родители, бабушки, водители: один взрослый переиспользуется в нескольких карточках,
  с ролью и отдельными настройками напоминаний; можно отметить, кто платит.
- **Группы** — до 10 участников, цена за урок с человека, постоянная ссылка на встречу и заметки.
- **Уроки** — индивидуальные, групповые, пробные и отработки; длительность, оплата ученика,
  оценка и комментарий для семьи; повторяющиеся серии с массовым изменением и удалением.
- **Домашние задания** — отдельная вкладка урока: задание, срок сдачи, статус, ссылка на запись,
  заметка для себя и комментарий для семьи.
- **Расписание** — недельный календарь с сеткой по четвертям часа, карточками занятий,
  слотами и отпусками, навигацией по неделям без перезагрузки страницы.
- **Аккаунт** — регистрация, вход, серверные сессии, восстановление пароля по одноразовой ссылке.

Данные каждого репетитора изолированы: запись другого аккаунта неотличима от несуществующей.

> **Статус проекта:** ранняя версия (`0.1.0`). Ученики, контакты, группы, уроки и ДЗ работают с базой данных;
> календарь пока наполняется детерминированными демо-данными — модель расписания в разработке.

## Почему стоит взять этот проект

- **Открытый код и MIT.** Никаких закрытых модулей и lock-in — код можно читать, менять и форкать.
- **Self-hosted.** База и данные лежат на вашем сервере. Ничего не уходит в чужое облако.
- **Развёртывание без DevOps.** Один процесс, один файл SQLite в качестве базы по умолчанию.
  Перенос на PostgreSQL — это смена `DATABASE_URL`.
- **Без сборки фронтенда.** Server-side rendering на Jinja2 + HTMX + Alpine.js: нет Node.js,
  npm-зависимостей и ночного CI, который перестаёт собираться.
- **Ассеты локально.** htmx, Alpine, иконки и стили отдаются из `app/static/` — без CDN
  и внешних запросов из браузера.
- **Понятная архитектура.** Доменные модули, один класс — один файл, строгие правила разработки
  в [AGENTS.md](AGENTS.md) и 600+ тестов.
- **Миграции и тесты из коробки.** Alembic для схемы, pytest для поведения.

## Технологии

Python 3.14 · FastAPI · Uvicorn · SQLAlchemy 2.0 · Alembic · SQLite · Jinja2 · HTMX · Alpine.js · pytest · [uv](https://docs.astral.sh/uv/)

## Быстрый старт

Нужен только [uv](https://docs.astral.sh/uv/) — Python 3.14 он подтянет сам.

```bash
git clone https://github.com/kuzmichus/open-tutor-crm.git
cd open-tutor-crm

uv sync                                  # окружение и зависимости
uv run alembic upgrade head              # схема БД (создаст tutor.db)
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Откройте <http://localhost:8000> → регистрация → личный кабинет.
Проверка живости: `GET /health` → `{"status": "ok"}`.

## Запуск на своём сервере

### Вариант A. systemd + Uvicorn (рекомендуется)

```bash
sudo git clone https://github.com/kuzmichus/open-tutor-crm.git /opt/open-tutor-crm
cd /opt/open-tutor-crm
sudo uv sync --no-dev
sudo uv run alembic upgrade head
sudo chown -R www-data:www-data /opt/open-tutor-crm
```

Каталог должен быть доступен сервисному пользователю на запись: SQLite создаёт рядом
с базой журнальные файлы.

`/etc/systemd/system/open-tutor-crm.service`:

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

Наружу отдавайте через nginx или Caddy: проксируйте на `127.0.0.1:8000`
и обязательно включите HTTPS — сессионная cookie ездит в браузере.

Для боевой установки используйте отдельный диск или том под `tutor.db`
(и его бэкапы) — файл базы переживёт перезапуски и обновления кода.

### Вариант B. Docker

Создайте `Dockerfile` в корне репозитория:

```dockerfile
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY . .
RUN uv sync --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Сборка, миграции и запуск:

```bash
docker build -t open-tutor-crm .

docker run --rm -v open_tutor_data:/data \
  -e DATABASE_URL=sqlite:////data/tutor.db \
  open-tutor-crm uv run alembic upgrade head

docker run -d --name open-tutor-crm \
  -p 8000:8000 \
  -v open_tutor_data:/data \
  -e DATABASE_URL=sqlite:////data/tutor.db \
  open-tutor-crm
```

Том `/data` хранит базу между перезапусками и пересборками контейнера.

### Обновление

```bash
git pull
uv sync --no-dev
uv run alembic upgrade head
sudo systemctl restart open-tutor-crm
```

Перед обновлением сделайте резервную копию базы: `cp tutor.db tutor.db.bak`.

### Когда пора на PostgreSQL

SQLite спокойно держит личный кабинет одного-двух репетиторов. Если пользователей
больше или нужен внешний бэкап-кластер — смените `DATABASE_URL` на строку подключения
PostgreSQL, добавьте драйвер (`uv add "psycopg[binary]"`) и прогоните миграции.
Код моделей при этом не меняется.

## Разработка

```bash
uv sync                                                # dev-группа зависимостей
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

При старте в режиме разработки таблицы создаются автоматически (`init_db` в lifespan).
Для воспроизводимой схемы всё равно используйте Alembic.

| Команда | Назначение |
|---|---|
| `uv run pytest` | все тесты |
| `uv run pytest -q tests/test_lesson_create.py` | конкретный файл |
| `uv run alembic upgrade head` | применить миграции |
| `uv run alembic revision --autogenerate -m "..."` | новая миграция |
| `uv run alembic current` / `downgrade -1` | текущая ревизия / откат одной |
| `uv run uvicorn main:app --reload` | dev-сервер |

### Конфигурация

Параметры читаются из переменных окружения или файла `.env` в корне проекта:

```env
DATABASE_URL=sqlite:///./tutor.db
APP_NAME=Open Tutor CRM
```

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./tutor.db` | строка подключения SQLAlchemy |
| `APP_NAME` | `Open Tutor CRM` | название приложения |

## Дорожная карта

- [x] Аккаунт репетитора: регистрация, вход, сессии, сброс пароля
- [x] Ученики и переиспользуемые контакты
- [x] Группы и состав групп
- [x] Уроки, серии и домашние задания
- [ ] Модель расписания: календарь из БД вместо демо-данных, слоты и отпуска
- [ ] Финансы: баланс ученика, списания и оплаты
- [ ] Напоминания ученикам и родителям
- [ ] Кабинет ученика и рассылки

## Участие в проекте

Issues и pull request'ы приветствуются. Перед PR:

1. Прочитайте [AGENTS.md](AGENTS.md) — там архитектурные правила проекта.
2. Добавьте тесты на новое поведение.
3. Убедитесь, что `uv run pytest` зелёный, а миграции созданы через autogenerate.

Вопросы и предложения — в Telegram: [@opentutorcrm](https://t.me/opentutorcrm).

## Лицензия

[MIT](LICENSE) © 2026 Sergey
