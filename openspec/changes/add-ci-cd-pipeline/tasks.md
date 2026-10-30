# Tasks

## 1. Проверки на push и pull_request

- [x] 1.1 Создать `.github/workflows/ci.yml` с триггерами `push` (все ветки),
      `pull_request` и `workflow_call`, ограничениями `permissions: contents: read`
      и группой `concurrency` с `cancel-in-progress: true`. Проверка: файл
      проходит `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"`
      и содержит все три триггера.

- [x] 1.2 Добавить джобу `tests`: `actions/checkout`, `astral-sh/setup-uv` с
      `enable-cache: true` и `python-version: "3.14"`, затем `uv sync --frozen`
      и `uv run pytest -n auto`. Проверка: локально `uv sync --frozen && uv run pytest -n auto`
      даёт 1864 passed; джоба зелёная в первом прогоне на PR.

- [x] 1.3 Добавить джобу `lock`: `uv lock --check`. Проверка: локально команда
      завершается с кодом 0; при правке `pyproject.toml` без `uv lock` джоба
      краснеет (проверить на временной ветке и откатить).

- [x] 1.4 Добавить джобу `migrations`: `DATABASE_URL=sqlite:///./ci-check.db
      uv run alembic upgrade head`, затем `uv run alembic check` с тем же
      `DATABASE_URL`. Проверка: локально на пустом файле обе команды завершаются
      успешно; после добавления поля в модель без миграции `alembic check`
      выходит с ненулевым кодом.

- [x] 1.5 Добавить джобу `lint`: `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py`.
      Проверка: локально команда печатает «All checks passed!»; при внесении
      заведомой синтаксической ошибки джоба краснеет.

- [x] 1.6 Добавить джобу `docker`: `docker/build-push-action` с `push: false`,
      `cache-from: type=gha`, `cache-to: type=gha,mode=max`, затем запуск
      контейнера с `-p 8000:8000` и ожидание ответа `{"status": "ok"}` от
      `GET /health` (таймаут и остановка контейнера в `if: always()`).
      Проверка: джоба зелёная; при удалении каталога из `COPY` в Dockerfile
      смоук падает.

- [x] 1.7 Проверить, что `ci.yml` не имеет права записи в репозиторий: убедиться,
      что `permissions` не содержит `contents: write` ни на уровне workflow, ни
      в джобах. Проверка: `grep -c "contents: write" .github/workflows/ci.yml`
      возвращает 0.

## 2. Версия приложения из манифеста

- [x] 2.1 Заменить литерал версии в `create_app()` на чтение из `pyproject.toml`
      через `tomllib` с модульной константой. Проверка: `uv run python -c "from main import app; print(app.version)"`
      печатает версию из `pyproject.toml`.

- [x] 2.2 Добавить `pyproject.toml` в `COPY` рантайм-стадии `Dockerfile`
      (рядом с `alembic.ini cron.py main.py`). Проверка: `docker build -t otc-check .`
      и `docker run --rm otc-check python -c "import main; print(main.app.version)"`
      печатают ту же версию, что в манифесте.

- [x] 2.3 Добавить тест в `tests/`, сравнивающий `app.openapi()["info"]["version"]`
      с версией из `pyproject.toml`. Проверка: `uv run pytest -q tests/test_app_version.py`
      зелёный; после смены версии в манифесте тест остаётся зелёным без правок.

## 3. Ручная публикация образа

- [x] 3.1 Создать `.github/workflows/release.yml` с единственным триггером
      `workflow_dispatch` и обязательным входом `version` (тип `string`).
      Проверка: в интерфейсе GitHub кнопка «Run workflow» требует заполнить
      поле; пуш в `main` workflow не запускает.

- [x] 3.2 Добавить джобу `verify-version`: сравнение входа `version` с версией
      из `pyproject.toml`, падение при расхождении до сборки. Проверка: ручной
      запуск с заведомо неверной версией завершается неуспешно, образ в реестр
      не попадает.

- [x] 3.3 Подключить проверки: джоба `publish` объявляет
      `uses: ./.github/workflows/ci.yml` (или `needs: verify-version` плюс
      вызов проверок), `permissions: contents: write`. Проверка: при красных
      тестах джоба публикации не выполняется.

- [x] 3.4 Добавить сборку и публикацию: `docker/setup-buildx-action`,
      `docker/login-action` с `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`,
      `docker/build-push-action` с `platforms: linux/amd64` и тегами
      `0.2.0`, `0.2`, `latest`, `sha-<short>`. Проверка: `docker manifest inspect`
      на опубликованном теге показывает одну архитектуру `amd64`, а в реестре
      видны все четыре тега.

- [x] 3.5 Создать git-тег `v<version>` последним шагом после успешного push
      образа. Проверка: после успешного запуска `git ls-remote --tags origin`
      содержит `v<version>`; при искусственной ошибке авторизации в реестр тег
      отсутствует.

- [x] 3.6 Убедиться, что секреты используются только в `release.yml` и только
      в джобе публикации. Проверка: `grep -rn "DOCKERHUB" .github/workflows/`
      находит вхождения только в `release.yml`.

## 4. Документация

- [x] 4.1 Описать в `README.md` автоматические проверки и выпуск релиза: какие
      проверки идут на PR, как запустить публикацию, какие теги получает образ,
      какие секреты нужны в настройках репозитория. Проверка: команды из раздела
      выполняются как написано (`docker pull` по указанному тегу работает после
      первой публикации).

- [x] 4.2 Обновить `AGENTS.md`: перечислить, что проверяется в CI и что
      публикация только ручная. Проверка: список проверок в `AGENTS.md`
      совпадает с джобами `ci.yml`.

## 5. Интеграционная проверка

- [ ] 5.1 Открыть PR с изменениями и убедиться, что все джобы зелёные и что
      повторный пуш отменяет предыдущий прогон (группа `concurrency`).
      Проверка: в списке запусков видно отменённый предыдущий run.

- [ ] 5.2 Выполнить пробную публикацию версии `0.1.0` и проверить цепочку
      целиком: тесты → образ → тег. Проверка: `docker pull kuzmichus/open-tutor-crm:0.1.0`
      запускается и отдаёт `/health`, тег `v0.1.0` есть в репозитории.

## Workflow follow-up

- Добавить в настройках репозитория секреты `DOCKERHUB_USERNAME` и
  `DOCKERHUB_TOKEN` (токен с правами Read/Write на `kuzmichus/open-tutor-crm`)
  до первой публикации.
- Заархивировать change после ревью.

## Реализация: всё, что проверялось локально, — зелёное

Задачи 1.1–1.7, 2.1–2.3, 3.1–3.6 и 4.1–4.2 выполнены. Джобы `ci.yml` и шаги
`release.yml` прогнаны на этой машине: 1866 тестов зелёные, `uv lock --check`
и узкий `ruff` чистые, `alembic check` на пустой базе отвечает «No new upgrade
operations detected», а на модели с лишней колонкой выходит с кодом 255.
Образ собирается, контейнер отдаёт `{"status": "ok"}`; при удалении каталога
`app/` или `pyproject.toml` из `COPY` смоук-проверка падает с `ModuleNotFoundError`
и `FileNotFoundError` соответственно — то есть ловит эти регрессии.

Осталось выполнить в GitHub (`gh` здесь не авторизован): 5.1 (первый прогон
workflow на PR) и 5.2 (пробная публикация `0.1.0`). Секреты Docker Hub нужно
добавить в настройках репозитория до первой публикации.
