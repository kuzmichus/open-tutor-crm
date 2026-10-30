# Образ Open Tutor CRM: FastAPI + Uvicorn, зависимости ставит uv из uv.lock.
# Двухэтапная сборка: uv и кэши остаются на этапе deps — в рантайм уходит
# только готовый .venv и исходники.
FROM python:3.14-slim AS deps

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

# Интерпретатор берём из базового образа (uv не качает свой), .pyc
# компилируются при установке — контейнер стартует быстрее.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Манифесты — отдельно от кода: правки исходников не сбрасывают кэш
# слоя установки зависимостей.
COPY pyproject.toml uv.lock ./

# --frozen — ровно как в uv.lock, без пере-резолвинга. Приложение не пакет
# (в pyproject нет [build-system]), поэтому --no-install-project: в venv
# нужен только сторонний код, исходники копируются рядом отдельным слоем.
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim

# Приложение не должно работать под root. SQLite создаёт рядом с базой
# журнальные файлы, поэтому том и рабочий каталог отдаются сервисному
# пользователю.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app

COPY --from=deps --chown=app:app /app/.venv ./.venv
# pyproject.toml нужен и в рантайме: из него читается версия приложения
# (app/__init__.py), иначе образ, git-тег релиза и app.version расходятся.
COPY --chown=app:app pyproject.toml alembic.ini cron.py main.py ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app

# База на томе /data: файл внутри контейнера пережил бы перезапуск,
# но пропал бы при пересборке образа.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/tutor.db

RUN mkdir /data && chown app:app /data
USER app

VOLUME /data
EXPOSE 8000

# /health (app/common/views/health.py); curl в slim нет — проверяем питоном.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
