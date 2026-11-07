# Tasks

## 1. Конфигурация и сервис режима

- [x] 1.1 `app/config.py`: поле `single_mode: bool = False` (`SINGLE_MODE`)
  с комментарием о режимах и требовании перезапуска.
- [x] 1.2 Новый `app/tutor/services/registration_mode.py`:
  `has_tutors(db)` — есть ли хоть один репетитор (`SELECT id LIMIT 1`);
  `is_first_run(db)` — сингл-режим и репетиторов нет;
  `registration_open(db)` — мульти-режим или первый запуск. `settings`
  читается в момент вызова, не при импорте.

## 2. Вьюхи

- [x] 2.1 `app/tutor/views/register.py`: `_ensure_registration_open(db)`
  поднимает `HTTPException(404)`; вызывается первым действием в `GET` и `POST`
  `/tutor/register`. В `register_form` добавлена зависимость `get_db`.
- [x] 2.2 `app/tutor/views/login.py`: `GET /tutor/login` при `is_first_run(db)`
  отвечает 303 на `/tutor/register`; возвращаемый тип — `Response`, иначе
  FastAPI пытается построить модель ответа из union.
- [x] 2.3 `app/tutor/views/login.py`: `_render` принимает `db` и передаёт
  `show_register=registration_open(db)` — и в GET, и в POST с ошибкой.
- [x] 2.4 `app/tutor/views/remember_password.py`: `GET` получает `db`, `_render`
  передаёт `show_register` в GET и POST.

## 3. Шаблоны

- [x] 3.1 `app/tutor/templates/tutor/login.html`: ссылка «Нет аккаунта?
  Зарегистрироваться» под `{% if show_register %}`.
- [x] 3.2 `app/tutor/templates/tutor/remember_password.html`: та же ссылка под
  `{% if show_register %}`.

## 4. Тесты

- [x] 4.1 Новый `tests/test_single_mode.py`: `Settings(_env_file=None)` по
  умолчанию `single_mode=False`, `SINGLE_MODE=true` из окружения включает
  режим.
- [x] 4.2 Мульти-режим: регистрация открыта при существующем репетиторе,
  `GET /tutor/login` не редиректит на пустой базе, ссылка на регистрацию есть.
- [x] 4.3 Сингл-режим, первый запуск: `GET /tutor/register` — 200,
  `GET /tutor/login` — 303 на `/tutor/register`, цепочка `/` с follow
  доходит до формы, `POST /tutor/register` создаёт репетитора.
- [x] 4.4 Сингл-режим после первого аккаунта: `GET` и `POST`
  `/tutor/register` — 404 (кастомная страница), второй репетитор не создаётся,
  `GET /tutor/login` — 200, ссылки на регистрацию нет на входе и на
  восстановлении пароля.
- [x] 4.5 Сингл-режим: после успешной регистрации страница сразу отдаёт 404 и
  по GET, и по POST.
- [x] 4.6 Прогон `uv run pytest -n auto` — 2373 теста зелёные; линт
  `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py`.

## 5. Спецификация и документация

- [x] 5.1 Delta-спека `tutor-auth`: MODIFIED «Регистрация репетитора» и «Вход
  в систему», ADDED «Режим работы CRM».
- [x] 5.2 `openspec/specs/tutor-auth/spec.md`: основная спека синхронизирована
  с дельтой.
- [x] 5.3 `README.md`: строка `SINGLE_MODE` в таблице «Конфигурация» и абзац о
  режимах после таблицы.
- [x] 5.4 `CHANGELOG.md`: пункт в `[Unreleased] → Добавлено`.
