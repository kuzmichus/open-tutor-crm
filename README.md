# Open Tutor CRM

**Открытая CRM для репетиторов: ученики, группы, уроки и расписание — на вашем собственном сервере.**

Один репетитор — один аккаунт — только его данные. Self-hosted: база и файлы лежат у вас
(SQLite по умолчанию, PostgreSQL — сменой `DATABASE_URL`), никаких подписок и облаков.
Рендеринг серверный на Jinja2 + HTMX + Alpine.js — без Node.js и сборки фронтенда; все
ассеты отдаются локально, без CDN. История версий — в [CHANGELOG.md](CHANGELOG.md).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![Docker Hub](https://img.shields.io/badge/Docker%20Hub-kuzmichus%2Fopen--tutor--crm-2496ED.svg)](https://hub.docker.com/r/kuzmichus/open-tutor-crm)

## Возможности

- **Главная** — дашборд «сегодня»: уроки дня, активные ученики, доход и проведённые часы за месяц.
- **Календарь** — недельная сетка по четвертям часа: уроки, окна для записи, отпуска и выходные, навигация по неделям.
- **Ученики** — карточки с контактами, статусом и долгом; переиспользуемые контакты взрослых с ролью и напоминаниями.
- **Группы** — до 10 участников, цена за урок с человека, вкладки занятий и оплат группы.
- **Уроки** — индивидуальные, групповые, пробные и отработки; серии с массовым изменением; отметка проведёнными пачкой.
- **Домашние задания** — вкладка урока: задание, срок сдачи, статус, ответ ученика и проверка.
- **Брони и публичная запись** — ученик записывается по ссылке без входа, заявка подтверждается в календаре и становится уроком.
- **Финансы** — сводка за период, все операции, аналитика и прогноз на месяц; счёт ученика: платежи, списания, возвраты, счёт за период.
- **Задачи** — канбан по этапам и список по срокам: приоритет, срок, привязка к ученикам.
- **Статистика** — LTV, Retention Rate, «риск потери», конверсия из пробного, выгрузка CSV.
- **Рассылки** — сегменты учеников, шаблоны с подстановками и журнал всех сообщений бота.
- **Мессенджеры** — Telegram и MAX: токен бота, каналы уведомлений и приглашения учеников по диплинку, без ручного ввода chat_id.
- **Кабинеты** — ученик (`/student`) видит неделю своих занятий в календаре (только чтение, со значками ДЗ) и сдаёт ДЗ, родитель (`/parent`) — детей, их занятия, ДЗ и финансы; входы независимы от сессии репетитора.
- **Оформление** — светлая и тёмная темы: выбор запоминается и не мигает при переходах.

Данные каждого репетитора изолированы: запись другого аккаунта неотличима от несуществующей.

## Быстрый старт (Docker Compose)

Нужен только Docker. Сохраните как `docker-compose.yaml`, запустите `docker compose up -d`, откройте <http://localhost:8000> → регистрация → главная с дашбордом. Живость: `GET /health` → `{"status": "ok"}`.

```yaml
services:
  migrate:                      # одноразовая миграция до старта приложения
    image: kuzmichus/open-tutor-crm:latest
    command: alembic upgrade head
    volumes: [open_tutor_data:/data]
    restart: "no"

  app:
    image: kuzmichus/open-tutor-crm:latest
    depends_on:
      migrate:
        condition: service_completed_successfully
    ports: ["8000:8000"]
    volumes: [open_tutor_data:/data]
    restart: unless-stopped

volumes:
  open_tutor_data:
```

Для стабильности зафиксируйте версию вместо `latest` (релизы публикуются с тегами `X.Y.Z`, `X.Y`, `sha-*`). Образ собирается для `linux/amd64` — на ARM-хосте соберите его локально (см. ниже). База живёт на томе `open_tutor_data` (`/data` в контейнере).

Cron — из crontab хоста раз в минуту (compose расписаний не умеет):

```bash
* * * * * cd /путь/к/каталогу/compose && docker compose run --rm app python cron.py
```

## Запуск на своём сервере

### Docker без compose

```bash
docker run --rm -v open_tutor_data:/data kuzmichus/open-tutor-crm:latest alembic upgrade head

docker run -d --name open-tutor-crm \
  -p 8000:8000 \
  -v open_tutor_data:/data \
  kuzmichus/open-tutor-crm:latest
```

Миграции — одноразовым контейнером **до** первого старта приложения: иначе таблицы создаст `init_db()` без записи в `alembic_version`, и последующий `alembic upgrade head` упадёт.

### Сборка образа локально

```bash
docker build -t open-tutor-crm .
```

Дальше те же команды с `open-tutor-crm` вместо `kuzmichus/open-tutor-crm:latest`; процесс
не под root, живость проверяет встроенный healthcheck (`GET /health`).

### Релизы образа

Публикация — только вручную: workflow `.github/workflows/release.yml` запускается на
Actions → **Release** → «Run workflow» с полем `version`, которое обязано совпадать с
версией в `pyproject.toml`. Каждый выпуск получает четыре тега: `X.Y.Z`, `X.Y`,
`latest` и `sha-<7 знаков>`; последним шагом создаётся релиз GitHub с тегом `v<version>`
(при ошибке реестра не появится ни релиза, ни тега). Секреты `DOCKERHUB_USERNAME` и
`DOCKERHUB_TOKEN` нужны только этому workflow — `ci.yml` запускается из форков без них.

### Без Docker: uv + systemd

Нужен только [uv](https://docs.astral.sh/uv/) — Python 3.14 он подтянет сам.

```bash
sudo git clone https://github.com/kuzmichus/open-tutor-crm.git /opt/open-tutor-crm
cd /opt/open-tutor-crm
sudo uv sync --no-dev
sudo uv run alembic upgrade head
sudo chown -R www-data:www-data /opt/open-tutor-crm   # SQLite пишет журнал рядом с базой
```

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

[Install]
WantedBy=multi-user.target
```

Запустите: `sudo systemctl daemon-reload && sudo systemctl enable --now open-tutor-crm`.
Наружу отдавайте через nginx или Caddy с HTTPS — сессионная cookie ездит в браузере.

Cron — раз в минуту. Задания: автозавершение уроков, не отмеченных 24 часа после окончания (списание — как при ручной отметке), дневная сводка уроков в мессенджеры и рассылка «День рождения».

- **Дневная сводка** — в время из профиля (вкладка «Уведомления», поле «Время отправки») во все привязанные каналы: время, ученик или группа и пометка, если на счету не хватает денег на урок.
- **День рождения** — в то же время, если включён переключатель «День рождения» на вкладке «Уведомления»: во все привязанные каналы уходит список учеников с днём рождения сегодня, с исполняющимся возрастом. Пустой список сообщения не даёт. Дата рождения 29 февраля в невисокосные годы в рассылку не попадает.

Задания идемпотентны и живут в своих транзакциях: одна отправка на локальные сутки педагога.

```bash
* * * * * cd /opt/open-tutor-crm && /opt/open-tutor-crm/.venv/bin/uv run python cron.py
```

## Конфигурация

Параметры читаются из переменных окружения или файла `.env` в корне проекта.

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./tutor.db` | строка подключения SQLAlchemy; в образе — `sqlite:////data/tutor.db` |
| `APP_NAME` | `Open Tutor CRM` | название приложения |
| `MESSENGER_TLS_VERIFY` | `true` | проверка TLS-сертификатов Bot API мессенджеров; `false` — на машинах без корня Минцифры (сертификат `platform-api2.max.ru`) |
| `MIGRATION_SOURCE_TZ` | системная зона сервера | зона-источник перевода старых записей в UTC; читается только `alembic upgrade`, например `MIGRATION_SOURCE_TZ=Europe/Berlin uv run alembic upgrade head` |

Время хранится в UTC, вводится и показывается в зоне репетитора (IANA-имя из его карточки); при пустом поле — зона сервера. SQLite держит кабинет одного-двух репетиторов; для большего смените `DATABASE_URL` на PostgreSQL, добавьте драйвер (`uv add "psycopg[binary]"`) и прогоните миграции — код моделей не меняется.

## Обновление

Перед обновлением сделайте резервную копию базы:

```bash
cp tutor.db tutor.db.bak                                    # git-установка
docker run --rm -v open_tutor_data:/data -v "$PWD:/backup" \
  python:3.14-slim cp /data/tutor.db /backup/tutor.db.bak   # docker-установка

# git-путь
git pull && uv sync --no-dev && uv run alembic upgrade head
sudo systemctl restart open-tutor-crm

# docker-путь
docker compose pull && docker compose run --rm migrate && docker compose up -d
```

## Дорожная карта

- [x] Аккаунт репетитора: регистрация, вход, сессии, сброс пароля
- [x] Ученики, переиспользуемые контакты и группы
- [x] Уроки, серии, домашние задания и календарь с недоступностью
- [x] Окна для записи и публичная страница записи
- [x] Финансы: баланс, списания, оплаты, возвраты, счёт за период
- [x] Задачи: канбан по этапам и список по срокам
- [x] Статистика: удержание, выручка, конверсия из пробного
- [x] Рассылки и мессенджеры: Telegram и MAX, каналы уведомлений, приглашения
- [x] Кабинеты ученика и родителя; светлая и тёмная темы
- [ ] Напоминания и повторные приглашения ученикам и родителям
- [ ] PostgreSQL-ветка

## Разработка

```bash
uv sync                                   # dev-зависимости
uv run uvicorn main:app --reload          # dev-сервер на :8000
uv run pytest -n auto                     # тесты
uv run alembic upgrade head               # схема БД
uv run alembic revision --autogenerate -m "..."   # новая миграция
uv run python scripts/seed_demo.py        # демо-данные в локальную базу
```

В dev-режиме таблицы создаёт `init_db()` при старте; для воспроизводимой схемы используйте Alembic. Правила разработки — в [AGENTS.md](AGENTS.md), спецификации поведения — в `openspec/specs/`.

### Демо-данные

`scripts/seed_demo.py` наполняет локальную базу правдоподобным учебным годом:
15 учеников (дети и взрослые), переиспользуемые контакты взрослых (в том числе
мама и папа двух детей), две группы с разными ценами участников, уроки с 1 сентября
по 25 мая (проведённые — с отметками неявок и списаниями, будущие — запланированные),
платежи с должниками и предоплатами, домашние задания, задачи и расходы.

```bash
uv run python scripts/seed_demo.py        # пересоздать демо-данные
uv run python scripts/smoke_demo.py       # проверить, что все страницы рендерятся
```

Скрипт **разрушающий**: данные репетитора `demo@example.com` удаляются и создаются
заново (остальные аккаунты в базе не затрагиваются). Вход после прогона —
`demo@example.com` / `12345678`. Списания за проведённые уроки считаются доменным
сервисом `sync_lesson_charge`, поэтому балансы в демо-базе совпадают с тем, что
показывает приложение.

## Участие в проекте

Issues и pull request'ы приветствуются: прочитайте [AGENTS.md](AGENTS.md), добавьте тесты
на новое поведение и убедитесь, что `uv run pytest -n auto` зелёный.

На каждый push и pull request параллельно идут автоматические проверки
(`.github/workflows/ci.yml`): тесты, `uv lock --check`, `alembic check`
(модель без миграции валит PR), линт `ruff check --select E9,F63,F7,F82`
и сборка образа с смоук-проверкой `GET /health`. Тот же набор идёт перед
публикацией релиза — красные тесты не уезжают в образ.
Вопросы и предложения — в Telegram: [@opentutorcrm](https://t.me/opentutorcrm).

## Лицензия

[MIT](LICENSE) © 2026 Sergey
