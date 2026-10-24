"""Ограничение частоты заявок (design.md D12).

Публичный POST — единственный неаутентифицированный маршрут, создающий
строки в БД. Полноценного rate limiting в проекте нет, а тянуть Redis ради
счётчика неоправданно: таблица в той же SQLite закрывает сценарий «одна
ссылка в чате и сотня заявок».

Ключ — `sha256(slot_id + грубый отпечаток клиента)`. Ни `slot_id`, ни адрес
клиента в открытом виде не хранятся: таблица не должна превращаться в лог
посетителей. Лимит считается **на конкретное окно**, поэтому перебор разных
окон одним клиентом не блокирует обычную запись, а спам по одному окну
отсекается.

Окно подсчёта — фиксированные 10 минут от начала окна (не скользящее):
скользящее требует хранить каждую попытку отдельно, а для защиты от
«нажал пять раз» достаточно фиксированного.

Строки старше суток удаляются при каждом обращении — отдельного
планировщика в проекте нет, а держать мусор незачем.

*Чего это не заменяет*: капчу и honeypot. Капча ухудшает конверсию записи,
а объём атаки на self-hosted несопоставим (design D12); honeypot можно
добавить позже без изменения модели.
"""

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.booking.models.booking_attempt import (
    BOOKING_ATTEMPT_LIMIT,
    BOOKING_ATTEMPT_RETENTION_HOURS,
    BOOKING_ATTEMPT_WINDOW_MIN,
    BookingAttempt,
)
from app.tutor.services.clock import as_utc

# Сообщение при превышении лимита. Подробности внутренней проверки не
# раскрываются (спека public-booking): ни числа попыток, ни окна времени.
RATE_LIMITED_MESSAGE = (
    "Слишком много заявок подряд. Попробуйте через несколько минут."
)

def attempt_key(slot_id: str, fingerprint: str) -> str:
    """Ключ счётчика: sha256 от «окно + отпечаток клиента».

    Хеш, а не конкатенация: в таблице не остаётся ни адреса клиента, ни
    связи «этот человек интересовался этим окном».
    """
    raw = f"{slot_id}:{fingerprint}".encode()
    return hashlib.sha256(raw).hexdigest()

def _window_start(now: datetime) -> datetime:
    """Начало текущего окна подсчёта: момент, усечённый до шага окна.

    Усечение в UTC-секундах от эпохи: окна идут подряд без пропусков и
    перекрытий, а привязка к «круглым» минутам не нужна — важна только
    длительность.
    """
    now = as_utc(now)
    step = BOOKING_ATTEMPT_WINDOW_MIN * 60
    epoch_seconds = int(now.timestamp())
    return datetime.fromtimestamp(
        epoch_seconds - epoch_seconds % step, tz=now.tzinfo
    )

def _purge_old(db: Session, now: datetime) -> None:
    """Удаляет счётчики старше срока хранения (design D12).

    Коммит нужен здесь же: `DELETE` без него остался бы в открытой
    транзакции и мог откатиться вместе с чужой ошибкой, а мусор копился бы
    незаметно. Отдельного планировщика в проекте нет.
    """
    cutoff = as_utc(now) - timedelta(hours=BOOKING_ATTEMPT_RETENTION_HOURS)
    deleted = db.execute(
        delete(BookingAttempt).where(BookingAttempt.window_start < cutoff)
    )
    if deleted.rowcount:
        db.commit()

def is_rate_limited(
    db: Session,
    slot_id: str,
    fingerprint: str,
    *,
    now: datetime,
) -> bool:
    """Исчерпан ли лимит заявок по этому окну для этого клиента.

    Проверка ничего не пишет: счётчик увеличивает `register_attempt`
    только после успешного создания заявки. Иначе неудачные попытки
    (опечатка в имени) съедали бы лимит и мешали человеку исправить форму.
    """
    _purge_old(db, now)
    key = attempt_key(slot_id, fingerprint)
    count = db.scalar(
        select(BookingAttempt.count).where(
            BookingAttempt.key == key,
            BookingAttempt.window_start == _window_start(now),
        )
    )
    return bool(count) and count >= BOOKING_ATTEMPT_LIMIT

def register_attempt(
    db: Session,
    slot_id: str,
    fingerprint: str,
    *,
    now: datetime,
) -> None:
    """Увеличивает счётчик заявок по окну; вызывается после создания брони.

    Гонка двух параллельных запросов ловится `UNIQUE(key, window_start)`:
    второй падает на ограничении, и попытка повторяется инкрементом уже
    существующей строки. Ошибку не пробрасываем — счётчик не должен
    ломать успешно созданную заявку.
    """
    key = attempt_key(slot_id, fingerprint)
    window_start = _window_start(now)

    row = db.scalars(
        select(BookingAttempt).where(
            BookingAttempt.key == key,
            BookingAttempt.window_start == window_start,
        )
    ).one_or_none()

    if row is not None:
        row.count += 1
        db.commit()
        return

    db.add(BookingAttempt(key=key, window_start=window_start, count=1))
    try:
        db.commit()
    except IntegrityError:
        # Параллельный запрос успел создать строку — увеличиваем её.
        db.rollback()
        existing = db.scalars(
            select(BookingAttempt).where(
                BookingAttempt.key == key,
                BookingAttempt.window_start == window_start,
            )
        ).one_or_none()
        if existing is not None:
            existing.count += 1
            db.commit()

def client_fingerprint(request) -> str:
    """Грубый отпечаток клиента для лимита: адрес и User-Agent.

    Прокси-заголовки (`X-Forwarded-For`) намеренно не разбираются: за
    обратным прокси их можно подделать, а приложение рассчитано на прямой
    запуск (self-hosted). `request.client` может быть None (тестовый
    транспорт) — тогда остаётся только User-Agent.
    """
    client = getattr(request, "client", None)
    host = getattr(client, "host", "") or ""
    agent = request.headers.get("user-agent", "")
    return f"{host}|{agent}"
