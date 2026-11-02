# Proposal

## Why

В интерфейсе нигде не видно, какая версия сервиса сейчас работает. Репетитор,
сообщающий о проблеме, и владелец сервера, проверяющий, применилось ли
обновление, вынуждены заходить в консоль или в `pyproject.toml` — а опубликованный
образ мог отстать от ветки. Ссылки на исходный код тоже нет: открытый проект
никак не обозначает, где он живёт.

## What Changes

- В подвал интерфейса добавляется ненавязчивая подпись сервиса: версия
  приложения (`v0.2.0` и т. п.) и значок-ссылка на репозиторий
  `https://github.com/kuzmichus/open-tutor-crm/`.
- Версия берётся из единственного источника — `pyproject.toml` (уже читается
  в `app/__init__.py` как `__version__`) и передаётся шаблонам глобальной
  переменной `app_version`. Литерала версии в разметке не появляется.
- Адрес репозитория лежит рядом с версией в коде (`__repository_url__`), а не
  литералом в шаблоне.
- Разметка подписи — один общий партиал `app/templates/_footer_signature.html`,
  который включается в подвал сайдбара репетитора, в подвалы кабинетов ученика
  и родителя, на страницы входа/регистрации репетитора, вход кабинетов и 404.
- Значок GitHub — inline SVG: в наборе Lucide нет брендовых иконок, а тянуть
  ради одного значка CDN запрещено (правило AGENTS.md п. 8).

## Capabilities

### New Capabilities

— (нет)

### Modified Capabilities

- `app-navigation`: добавляется требование «Подпись сервиса в подвале» —
  версия из манифеста, ссылка на исходники и её наличие на поверхностях
  с сайдбаром и без.

## Impact

- **Код**: `app/__init__.py` (адрес репозитория), `app/templating.py`
  (глобальные переменные `app_version`, `app_repository_url`).
- **Шаблоны**: новый `app/templates/_footer_signature.html`;
  `app/templates/sidebar.html`, `app/templates/auth.html`,
  `app/templates/404.html`, `app/cabinet/templates/cabinet/base.html`,
  `app/cabinet/templates/cabinet/_sidebar.html`,
  `app/cabinet/templates/cabinet/parent/_sidebar.html`.
- **Стили**: `app/static/styles.css` — `.app-signature*`, `.auth__stack`,
  `.cabinet__signature`, правило для свёрнутого сайдбара.
- **Тесты**: новый `tests/test_footer_signature.py` (13 проверок).
- **Спецификации**: `openspec/specs/app-navigation/spec.md` — после
  синхронизации delta-spec.
- **Вне объёма**: кнопка «Проверить обновления», запрос к GitHub API за
  последней версией, показ git-хэша или даты сборки.
- **CHANGELOG.md**: строка о подписи добавляется при релизе, не отдельным
  коммитом.
