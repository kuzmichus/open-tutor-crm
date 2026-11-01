"""Состояние подключения календаря: токены и признаки в `tutor_params`.

Отдельная таблица не нужна: KV-хранилище репетитора (`app/tutor/services/params.py`)
для этого и существует (design D3). Ключи — с общим префиксом `google_`,
чтобы отключение и диагностика работали по одному списку.

Две формы записи, как у остальных потребителей параметров: `save_*` —
только изменения в текущей транзакции (cron коммитит сам), `set_*` —
изменения плюс коммит (действия пользователя в веб-запросе).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.gcalendar.models.calendar_event import DEFAULT_CALENDAR_ID
from app.gcalendar.services import oauth
from app.gcalendar.services.errors import GoogleApiError
from app.tutor.services.params import (
    all_params,
    delete_param,
    get_param,
    save_param,
    set_param,
)
from app.tutor.services.clock import as_utc, utcnow

# Имена параметров: один список — одна операция «удалить всё про Google».
REFRESH_TOKEN_KEY = "google_refresh_token"
ACCESS_TOKEN_KEY = "google_access_token"
ACCESS_EXPIRES_KEY = "google_access_expires_at"
ACCOUNT_EMAIL_KEY = "google_account_email"
CALENDAR_ID_KEY = "google_calendar_id"
OAUTH_STATE_KEY = "google_oauth_state"
LAST_ERROR_KEY = "google_last_error"

# Все ключи интеграции: отключение и сброс состояния удаляют их целиком.
ALL_KEYS = (
    REFRESH_TOKEN_KEY,
    ACCESS_TOKEN_KEY,
    ACCESS_EXPIRES_KEY,
    ACCOUNT_EMAIL_KEY,
    CALENDAR_ID_KEY,
    OAUTH_STATE_KEY,
    LAST_ERROR_KEY,
)

# Запас до истечения access_token: обновляем заранее, чтобы запрос не
# упал на 401 посреди синхронизации из-за пары секунд разницы часов.
EXPIRY_MARGIN = timedelta(seconds=60)

def is_connected(db: Session, tutor_id: str) -> bool:
    """Календарь подключён: сохранён refresh_token.

    Именно refresh_token, а не access_token: access живёт час и его
    отсутствие — штатное состояние между запросами.
    """
    return bool(get_param(db, tutor_id, REFRESH_TOKEN_KEY))

def account_email(db: Session, tutor_id: str) -> str:
    """Email подключённого аккаунта для подписи карточки (может быть пустым)."""
    return get_param(db, tutor_id, ACCOUNT_EMAIL_KEY) or ""

def refresh_token(db: Session, tutor_id: str) -> str:
    """Сохранённый refresh_token (пустая строка — календарь не подключён).

    Нужен отключению: токен отзывается в Google до того, как локальные
    параметры будут удалены.
    """
    return get_param(db, tutor_id, REFRESH_TOKEN_KEY) or ""

def calendar_id(db: Session, tutor_id: str) -> str:
    """Календарь, в который пишутся события; по умолчанию — основной."""
    return get_param(db, tutor_id, CALENDAR_ID_KEY) or DEFAULT_CALENDAR_ID

def last_error(db: Session, tutor_id: str) -> str:
    """Текст последней ошибки синхронизации для карточки (пусто — не было)."""
    return get_param(db, tutor_id, LAST_ERROR_KEY) or ""

def save_tokens(
    db: Session,
    tutor_id: str,
    *,
    refresh_token: str | None,
    access_token: str,
    expires_in: int | None,
    account_email: str = "",
    calendar_id_value: str = DEFAULT_CALENDAR_ID,
) -> None:
    """Сохраняет токены подключения в текущей транзакции (без коммита).

    `refresh_token` может отсутствовать: Google отдаёт его только при
    первом согласии, при повторном подключении приходит лишь access.
    Тогда прежний refresh_token не затирается пустым значением.
    """
    if refresh_token:
        save_param(db, tutor_id, REFRESH_TOKEN_KEY, refresh_token)
    save_param(db, tutor_id, ACCESS_TOKEN_KEY, access_token)
    if expires_in:
        expires_at = utcnow() + timedelta(seconds=int(expires_in))
        save_param(db, tutor_id, ACCESS_EXPIRES_KEY, expires_at.isoformat())
    if account_email:
        save_param(db, tutor_id, ACCOUNT_EMAIL_KEY, account_email)
    save_param(db, tutor_id, CALENDAR_ID_KEY, calendar_id_value or DEFAULT_CALENDAR_ID)
    # Успешное подключение снимает прежнюю ошибку: карточка не должна
    # показывать «требуется повторное подключение» после нового входа.
    delete_param(db, tutor_id, LAST_ERROR_KEY)

def set_last_error(db: Session, tutor_id: str, message: str) -> None:
    """Запоминает текст ошибки для карточки (пусто — очищает)."""
    if message:
        set_param(db, tutor_id, LAST_ERROR_KEY, message)
    else:
        delete_param(db, tutor_id, LAST_ERROR_KEY)

def save_oauth_state(db: Session, tutor_id: str, state: str) -> None:
    """Одноразовый `state` ссылки согласия — защита от подмены callback."""
    set_param(db, tutor_id, OAUTH_STATE_KEY, state)

def take_oauth_state(db: Session, tutor_id: str) -> str | None:
    """Читает и гасит `state`: второй callback с тем же значением отклоняется."""
    state = get_param(db, tutor_id, OAUTH_STATE_KEY)
    if state is not None:
        delete_param(db, tutor_id, OAUTH_STATE_KEY)
    return state

def clear(db: Session, tutor_id: str) -> None:
    """Удаляет все параметры интеграции (отключение календаря)."""
    for key in ALL_KEYS:
        delete_param(db, tutor_id, key)

def access_token(db: Session, tutor_id: str) -> str | None:
    """Действующий access_token; истёкший обновляется по refresh_token.

    Возвращает `None`, если календарь не подключён. Ошибки обновления
    пробрасываются (`GoogleApiError`/`GoogleReauthRequired`): решение
    «что делать» принимает вызывающая сторона — веб-действие пишет
    текст в карточку, cron — в лог.
    """
    refresh_token = get_param(db, tutor_id, REFRESH_TOKEN_KEY)
    if not refresh_token:
        return None

    token = get_param(db, tutor_id, ACCESS_TOKEN_KEY)
    if token and not _expired(get_param(db, tutor_id, ACCESS_EXPIRES_KEY)):
        return token

    return _refresh(db, tutor_id, refresh_token)

def force_refresh(db: Session, tutor_id: str) -> str | None:
    """Принудительно обновляет access_token (после 401 от API)."""
    refresh_token = get_param(db, tutor_id, REFRESH_TOKEN_KEY)
    if not refresh_token:
        return None
    return _refresh(db, tutor_id, refresh_token)

def _refresh(db: Session, tutor_id: str, refresh_token: str) -> str:
    """Обмен refresh_token на новый access_token и сохранение результата."""
    body = oauth.refresh_access_token(refresh_token)
    token = str(body.get("access_token") or "")
    if not token:
        raise GoogleApiError("Google: сервер не вернул access_token.")
    save_tokens(
        db,
        tutor_id,
        refresh_token=None,  # при обновлении Google его не присылает
        access_token=token,
        expires_in=body.get("expires_in"),
    )
    db.commit()
    return token

def _expired(raw: str | None) -> bool:
    """Срок access_token истёк (или неизвестен — тогда считаем истёкшим).

    Неизвестный срок трактуется как «истёк»: лишнее обновление дешевле
    запроса, который вернёт 401 и всё равно потребует обновления.
    """
    if not raw:
        return True
    try:
        expires_at = datetime.fromisoformat(raw)
    except ValueError:
        return True
    return as_utc(expires_at) - EXPIRY_MARGIN <= datetime.now(UTC)

def params_snapshot(db: Session, tutor_id: str) -> dict[str, str]:
    """Все параметры репетитора одним запросом (для отладочных проверок)."""
    return all_params(db, tutor_id)
