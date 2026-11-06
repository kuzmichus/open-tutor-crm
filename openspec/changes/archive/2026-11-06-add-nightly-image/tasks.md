# Tasks

## 1. Workflow ночной сборки

- [x] 1.1 Создать `.github/workflows/nightly.yml`: шапка-комментарий (почему
      отдельный файл, а не триггер в release.yml — design.md, решение 1);
      триггеры `schedule` с cron `17 0 * * *` и `workflow_dispatch`; 
      `permissions: contents: read`; `concurrency` с группой `nightly` и
      `cancel-in-progress: false`. Верификация: YAML разбирается парсером
      (например `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/nightly.yml'))"`;
      если PyYAML в системе нет — actionlint или GitHub при первом запуске),
      триггеры, permissions и concurrency соответствуют design.md.
- [x] 1.2 Добавить джобы: `checks` с `uses: ./.github/workflows/ci.yml` и
      `publish` с `needs: [checks]` — checkout, `docker/setup-buildx-action@v4`,
      `docker/login-action@v4` на секретах `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`,
      шаг тегов ровно с одним тегом `kuzmichus/open-tutor-crm:night`,
      `docker/build-push-action@v7` с `platforms: linux/amd64`, `push: true`
      и gha-кэшем (design.md, решения 2, 3, 7, 8). Верификация: сверка шагов с
      release.yml (те же экшены и пины), в списке тегов нет `latest`, версии и
      `sha-*`; нет шагов создания git-тега и релиза.

## 2. Согласование со спецификацией ci-cd-pipeline

- [x] 2.1 В
      `openspec/changes/add-ci-cd-pipeline/specs/ci-cd-pipeline/spec.md`
      уточнить формулировку требования «Публикация запускается только вручную
      с указанием версии»: запрет на расписание свести к релизному каналу
      (ночная публикация — отдельная спецификация `nightly-image`); сценарии и
      остальные требования не трогать. Верификация:
      `openspec validate add-ci-cd-pipeline` проходит, сценарии требования не
      изменились.

## 3. Документация

- [x] 3.1 README: в раздел «Релизы образа» добавить абзац про ночной образ —
      ежедневный запуск по расписанию, тег `night`, публикация только при
      зелёных проверках, чем ночной канал отличается от релизного (без git-тегов
      и релизов, `latest` не двигается). Верификация: описание совпадает с
      фактическим содержимым nightly.yml.
- [x] 3.2 CHANGELOG.md: запись про ночной образ в `[Unreleased] → Добавлено`.
      Верификация: формат Keep a Changelog сохранён, запись согласована с
      README.

## 4. Итоговые проверки

- [x] 4.1 `openspec validate add-nightly-image` проходит, включая `--strict`;
      `openspec status --change add-nightly-image` — все артефакты готовы.
- [ ] 4.2 После merge в `main`: запустить nightly.yml вручную
      (Actions → «Run workflow»), убедиться, что проверки зелёные, тег `night`
      в Docker Hub обновился и соответствует HEAD `main`, а релизные теги
      (`latest`, версия, `sha-*`) не изменились; на следующий день убедиться,
      что ночной запуск произошёл автоматически по расписанию.

## Workflow follow-up

- Архивировать change после ревью и успешного прогона, как принято в проекте.
- При архивации `add-ci-cd-pipeline` проверить, что уточнённая в задаче 2.1
  формулировка попадает в main-спеку без противоречий со спецификацией
  `nightly-image`.
