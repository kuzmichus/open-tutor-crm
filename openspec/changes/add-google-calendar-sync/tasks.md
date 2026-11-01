# Tasks

## 1. Конфигурация и схема

- [x] 1.1 `app/config.py`: `google_client_id`, `google_client_secret`,
  `google_redirect_uri` (пусто — собирается из запроса), `google_calendar_sync`
  (общий выключатель). Проверка: `tests/test_gcalendar_oauth.py::test_not_configured_by_default`,
  `::test_configured_needs_both_values` — зелёные.
- [x] 1.2 `app/gcalendar/models/calendar_event.py`: таблица `calendar_events`
  (`lesson_id` PK, FK на `lessons` с `ON DELETE CASCADE`, `event_id`,
  `calendar_id` с дефолтом `primary`, `content_hash`, `synced_at`); регистрация
  модели в `app/models.py`.
- [x] 1.3 `alembic/versions/c4b7a1f90d21_add_calendar_events.py`
  (`down_revision = 'ea9ed99a62d2'`). Проверка: `alembic upgrade head` и
  `alembic check` — дрейфа нет.

## 2. OAuth и состояние подключения

- [x] 2.1 `app/gcalendar/services/errors.py`: `GoogleError` и подклассы
  `GoogleNotConfigured`, `GoogleApiError`, `GoogleUnauthorized`,
  `GoogleReauthRequired`.
- [x] 2.2 `app/gcalendar/services/oauth.py`: `configured`, `build_auth_url`
  (`access_type=offline`, `prompt=consent`, scope `calendar.events` + `openid
  email`), `exchange_code`, `refresh_access_token` (разбор `invalid_grant`),
  `revoke_token`, `fetch_account_email`; HTTP — `urllib` с таймаутом 10 с.
- [x] 2.3 `app/gcalendar/services/redirect.py`: `redirect_uri(request)` — из
  `GOOGLE_REDIRECT_URI`, иначе из запроса; один и тот же адрес в ссылке
  согласия и в обмене кода.
- [x] 2.4 `app/tutor/services/params.py`: `forget_param` — удаление без коммита
  (атомарное подключение и отключение).
- [x] 2.5 `app/gcalendar/services/connection.py`: ключи `google_*`, `is_connected`
  (по `refresh_token`), `account_email`, `calendar_id`, `last_error`,
  `save_tokens(commit=...)`, `set_last_error`, `save_oauth_state`,
  `take_oauth_state` (одноразовый), `clear`, `access_token` с обновлением по
  сроку, `force_refresh`. Проверка: `tests/test_gcalendar_oauth.py` — зелёный.

## 3. События и синхронизация

- [x] 3.1 `app/gcalendar/services/api.py`: `insert_event`, `patch_event`,
  `delete_event` (404/410 — успех), `list_event_ids`; `sendUpdates=none`;
  один повтор после 401 через callable `refresh`.
- [x] 3.2 `app/gcalendar/services/event_payload.py`: `build_event` — заголовок
  «Занятие — имя» / «Занятие — Группа: имя», описание из типа, стоимости,
  заметки и ссылки, время в зоне педагога с локальным концом; `content_hash`.
- [x] 3.3 `app/gcalendar/services/mapping.py`: `get`, `upsert`, `forget`,
  `forget_tutor`, `event_ids_of_tutor`; выборки через `students`/`groups`.
- [x] 3.4 `app/gcalendar/services/sync.py`: `enabled`, `sync_lesson`
  (создать/обновить/пропустить по хешу), `sync_lessons`, `delete_lesson_event`,
  `build_payload`, `log_failure`, сброс подключения при `invalid_grant`.
  Проверка: `tests/test_gcalendar_sync.py` — зелёный.
- [x] 3.5 `app/gcalendar/services/initial_sync.py`: `sync_upcoming` — занятия
  со `starts_at >= сейчас`, по возрастанию времени, best-effort счётчики
  `(создано, обновлено, ошибок)`.
- [x] 3.6 `app/gcalendar/services/reconcile.py`: `reconcile_all` (по
  репетитору транзакция и коммит, падение изолировано) и `reconcile_tutor`
  (окно `RECONCILE_PAST_DAYS=1`, `RECONCILE_FUTURE_DAYS=90`, удаление
  осиротевших событий только если они есть в Google). Проверка:
  `tests/test_gcalendar_reconcile.py` — зелёный.

## 4. Профиль

- [x] 4.1 `app/gcalendar/services/presentation.py`: `google_calendar_context`
  (`configured`, `connected`, `account_email`, `calendar_id`, `last_error`,
  `connect_url`, `disconnect_url`, `sync_enabled`) и `google_error_message`
  (коды `not_configured`, `denied`, `state`, `exchange`, `failed`).
- [x] 4.2 `app/tutor/views/profile_google_connect.py`: `GET
  /tutor/profile/google/connect` — одноразовый `state` и редирект на согласие;
  без кредов — возврат на вкладку с подсказкой.
- [x] 4.3 `app/tutor/views/profile_google_callback.py`: `GET
  /tutor/profile/google/callback` — сверка и гашение `state`, отказ
  пользователя, обмен кода тем же `redirect_uri`, сохранение токенов и email,
  первичная выгрузка будущих занятий.
- [x] 4.4 `app/tutor/views/profile_google_disconnect.py`: `POST
  /tutor/profile/google/disconnect` — best-effort отзыв токена, удаление
  соответствий и параметров; уроки и события в Google остаются.
- [x] 4.5 `app/tutor/views/__init__.py`: регистрация трёх роутеров;
  `app/tutor/views/profile.py` — параметр `google_error`;
  `app/tutor/services/profile_page.py` — `google_calendar` в контексте вкладки
  «Календарь».
- [x] 4.6 `app/tutor/templates/tutor/_google_calendar_block.html` — карточка
  «Google Календарь» (неактивная кнопка и подсказка без кредов, состояние
  подключения с email, «Отключить», текст последней ошибки, предупреждение при
  `sync_enabled=False`); вставка в `_tab_calendar.html`. Проверка:
  `tests/test_gcalendar_views.py` — зелёный.

## 5. Хуки жизненного цикла урока

- [x] 5.1 `app/lesson/views/create.py`: создание урока (в т.ч. серии) —
  синхронизация после коммита.
- [x] 5.2 `app/lesson/views/update.py`: правка урока и `series_all` —
  синхронизация после коммита.
- [x] 5.3 `app/lesson/views/move.py`: перенос времени — правка события.
- [x] 5.4 `app/lesson/views/delete.py`: событие удаляется **до** урока.
- [x] 5.5 `app/lesson/views/delete_series.py`: события серии удаляются до
  уроков.
- [x] 5.6 `app/group/views/delete_group.py`: события всех уроков группы — до
  каскадного удаления группы.
- [x] 5.7 `app/booking/views/confirm.py`: подтверждение брони создаёт урок —
  событие после коммита.
- [x] 5.8 `app/common/services/cron.py`: `("gcalendar.reconcile",
  reconcile_all)` в `TASKS`.

## 6. Тесты

- [x] 6.1 `tests/test_gcalendar_oauth.py`: креды не заданы по умолчанию; ссылка
  согласия содержит client_id, scope и state; обмен кода идёт с тем же
  `redirect_uri`; `invalid_grant` требует повторного подключения; ошибка
  эндпоинта и сетевая ошибка — `GoogleApiError`; access обновляется по сроку и
  переиспользуется; `clear` удаляет все ключи; `state` одноразовый.
- [x] 6.2 `tests/test_gcalendar_sync.py`: создание события с локальным временем;
  правка при смене времени; отсутствие запросов при неизменном уроке; пропуск
  без подключения и при `GOOGLE_CALENDAR_SYNC=false`; ошибка API не поднимает
  исключение; 401 обновляет токен; удаление снимает строку и событие; вьюхи
  создания, правки, переноса, удаления урока, серии и группы синхронизируют;
  чужой урок не синхронизируется.
- [x] 6.3 `tests/test_gcalendar_views.py`: три маршрута без сессии дают редирект
  на вход; блок на вкладке в трёх состояниях (нет кредов, не подключён,
  подключён) и с текстом ошибки; подключение уводит на Google со `state`;
  callback с неверным и повторным `state` ничего не сохраняет; отказ
  пользователя и сбой обмена не оставляют полуподключения; токены, email и
  выгрузка только будущих занятий; отключение чистит параметры и соответствия,
  переживает сбой отзыва и не трогает уроки.
- [x] 6.4 `tests/test_gcalendar_reconcile.py`: задание в `TASKS` и вызываемое;
  создаёт пропущенное; идемпотентно; пропускает неподключённых; игнорирует
  уроки вне окна; удаляет осиротевшее событие; падение одного репетитора не
  мешает остальным; `invalid_grant` сбрасывает подключение.
- [x] 6.5 `uv run pytest -q -n 8` — набор зелёный (1985 passed).

## 7. Документация

- [x] 7.1 `README.md`: раздел «Как подключить Google Календарь» (создание
  OAuth-клиента, redirect URI, переменные окружения, что происходит после
  подключения, поведение «Отключить», предупреждение о восстановлении из
  бэкапа), строки `GOOGLE_*` в таблице конфигурации, пункт в «Возможностях»,
  сверка в разделе Cron.
- [x] 7.2 `CHANGELOG.md` (Unreleased): запись об интеграции с Google Календарём.
- [x] 7.3 OpenSpec change `add-google-calendar-sync`: `proposal.md`, `design.md`,
  `tasks.md`, спека `google-calendar-sync` и delta к `tutor-profile-settings`.

## 8. Проверки

- [x] 8.1 `uvx ruff@0.15.20 check --select E9,F63,F7,F82 app/ tests/ main.py cron.py` — чисто.
- [x] 8.2 `openspec validate add-google-calendar-sync --strict` — change валиден.
- [x] 8.3 Миграция применяется и откатывается, `alembic check` дрейфа не даёт.

## Workflow follow-up

- Синхронизировать и архивировать change после ревью.
