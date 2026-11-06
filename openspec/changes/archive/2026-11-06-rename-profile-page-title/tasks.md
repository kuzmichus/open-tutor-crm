# Tasks

## 1. Шаблон страницы

- [x] 1.1 В `app/tutor/templates/tutor/profile.html` заменить текст блока title на
  `Профиль — Open Tutor CRM`. Проверка: HTML страницы содержит
  `<title>Профиль — Open Tutor CRM</title>`.
- [x] 1.2 Там же заменить `<h1>Настройки</h1>` на `<h1>Профиль</h1>`, подзаголовок
  строки 27 и классы `.page-header` не трогать. Проверка: HTML содержит `<h1>Профиль</h1>`,
  табы и формы не изменились.

## 2. Тесты

- [x] 2.1 В `tests/test_profile.py` (`test_default_tab_is_profile`) убрать общую проверку
  `"Настройки" in response.text` и добавить точные проверки `<title>` и `<h1>`.
  Проверка: `uv run pytest tests/test_profile.py -n auto` — зелёный.

## 3. Спецификация

- [x] 3.1 Добавить change `rename-profile-page-title` с delta-spec на
  `tutor-profile-settings`: в требовании «Страница настроек с четырьмя вкладками»
  заголовок «Настройки» заменён на «Профиль», остальные утверждения и сценарии
  сохранены. Проверка: `openspec validate rename-profile-page-title --strict`.
- [x] 3.2 Синхронизировать `openspec/specs/tutor-profile-settings/spec.md`
  (строка 9: «заголовок «Профиль»»). Проверка: спека совпадает с поведением страницы.

## 4. Регресс

- [x] 4.1 Полный прогон `uv run pytest -n auto` — набор зелёный.
- [x] 4.2 Линт `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py` —
  без ошибок.

## Workflow follow-up

- Строку «Исправлено: заголовок страницы /tutor/profile — «Профиль»» добавить в
  `CHANGELOG.md` при следующем релизе (не отдельным коммитом).
- Архивировать change после ревью (`openspec archive rename-profile-page-title`).
