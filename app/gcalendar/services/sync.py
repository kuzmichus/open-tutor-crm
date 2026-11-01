"""Синхронизация урока с Google Календарём: создать, обновить, удалить.

Точка входа для вьюх — `sync_lesson`, `sync_lessons` и
`delete_lesson_event`. Домен уроков про Google не знает (design D2):
вьюха сохраняет урок своей транзакцией, а потом зовёт синхронизацию.

Правила (design D4, D6, D10):

- календарь не подключён или синхронизация выключена флагом
  `GOOGLE_CALENDAR_SYNC` — вызовов к API нет вовсе;
- хеш тела совпал с сохранённым — запроса к Google нет (правка статуса,
  оценки или комментария для семьи событие не меняет);
- ошибка Google не ломает действие пользователя: урок уже сохранён,
  ошибка уходит в лог и в параметр `google_last_error` для карточки;
- `invalid_grant` (доступ отозван) сбрасывает подключение: карточка
  предложит подключиться заново, остальной функционал работает.

Исход вызова — строка `OUTCOME_*`, а не `bool`: первичной выгрузке нужно
различать «создано», «обновлено» и «не удалось», чтобы показать счётчики
в карточке, а `bool` склеивал бы пропуск и ошибку.
"""

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.gcalendar.services import api, connection, event_payload, mapping
from app.gcalendar.services.errors import (
    GoogleApiError,
    GoogleReauthRequired,
    GoogleUnauthorized,
)
from app.group.models.group import Group
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student
from app.student.services.presentation import student_full_name

logger = logging.getLogger("gcalendar")

# Текст для карточки при отозванном доступе: репетитору нужно действие,
# а не техническая причина.
REAUTH_HINT = "Доступ к Google Календарю отозван — подключите его заново."

# Исходы синхронизации одного урока.
OUTCOME_CREATED = "created"
OUTCOME_UPDATED = "updated"
OUTCOME_SKIPPED = "skipped"  # не подключено или событие не изменилось
OUTCOME_FAILED = "failed"    # Google ответил ошибкой (уже в логе и карточке)

def enabled(db: Session, tutor_id: str) -> bool:
    """Синхронизация возможна: включена флагом и календарь подключён."""
    return settings.google_calendar_sync and connection.is_connected(db, tutor_id)

def sync_lesson(db: Session, tutor, lesson: Lesson) -> str:
    """Создаёт или обновляет событие урока; возвращает `OUTCOME_*`.

    Коммит делает сам: в веб-запросе урок уже сохранён отдельной
    транзакцией (`lesson_writer`), а строка соответствия должна уйти
    вместе с запросом к Google — иначе при падении процесса после
    создания события id потерялся бы и сверка создала бы дубль.
    """
    if not enabled(db, tutor.id):
        return OUTCOME_SKIPPED

    payload = build_payload(db, lesson, tutor)
    digest = event_payload.content_hash(payload)
    row = mapping.get(db, lesson.id)

    if row is not None and row.content_hash == digest:
        # Урок не менялся по существу (или менялись только поля, которых
        # нет в событии) — лишний запрос к Google не нужен.
        return OUTCOME_SKIPPED

    calendar_id = connection.calendar_id(db, tutor.id)
    try:
        if row is None:
            event_id = _call(
                db,
                tutor.id,
                lambda token: api.insert_event(token, calendar_id, payload),
            )
            mapping.upsert(
                db,
                lesson.id,
                event_id=event_id,
                calendar_id=calendar_id,
                content_hash=digest,
            )
            outcome = OUTCOME_CREATED
        else:
            _call(
                db,
                tutor.id,
                lambda token: api.patch_event(
                    token, row.calendar_id or calendar_id, row.event_id, payload
                ),
            )
            mapping.upsert(
                db,
                lesson.id,
                event_id=row.event_id,
                calendar_id=row.calendar_id or calendar_id,
                content_hash=digest,
            )
            outcome = OUTCOME_UPDATED
    except GoogleReauthRequired:
        _handle_reauth(db, tutor.id)
        return OUTCOME_FAILED
    except GoogleApiError as exc:
        log_failure(db, tutor.id, exc)
        return OUTCOME_FAILED

    db.commit()
    return outcome

def sync_lessons(db: Session, tutor, lessons: list[Lesson]) -> list[str]:
    """Синхронизирует пачку уроков (серия); исходы по каждому."""
    return [sync_lesson(db, tutor, lesson) for lesson in lessons]

def delete_lesson_event(db: Session, tutor, lesson: Lesson) -> bool:
    """Удаляет событие урока в Google.

    Вызывается **до** удаления урока: строка `calendar_events` уходит
    каскадом вместе с ним, и после удаления id события уже не узнать
    (design D7). `True` — событие было и Google его принял.
    """
    if not enabled(db, tutor.id):
        return False

    row = mapping.get(db, lesson.id)
    if row is None:
        return False

    ok = True
    try:
        _call(
            db,
            tutor.id,
            lambda token: api.delete_event(token, row.calendar_id, row.event_id),
        )
    except GoogleReauthRequired:
        _handle_reauth(db, tutor.id)
        ok = False
    except GoogleApiError as exc:
        log_failure(db, tutor.id, exc)
        ok = False
    finally:
        # Связь забывается в любом случае: урок всё равно удаляется, а
        # строка ушла бы каскадом. Осиротевшее событие в Google (если
        # запрос не прошёл) останется видимым — это лучше, чем вечная
        # ошибка на каждой попытке удаления.
        mapping.forget(db, lesson.id)
        db.commit()
    return ok

def build_payload(db: Session, lesson: Lesson, tutor) -> dict:
    """Тело события из урока и имён его цели."""
    student_name = None
    group_name = None
    if lesson.student_id:
        student = db.get(Student, lesson.student_id)
        student_name = student_full_name(student) if student is not None else None
    if lesson.group_id:
        group = db.get(Group, lesson.group_id)
        group_name = group.name if group is not None else None
    return event_payload.build_event(
        lesson,
        tutor,
        student_name=student_name,
        group_name=group_name,
    )

def _call(db: Session, tutor_id: str, action):
    """Вызов API с одним повтором после обновления access_token.

    401 означает истёкший или отозванный access_token: просим свежий у
    `connection` и повторяем запрос ровно один раз (design D6).
    """
    token = connection.access_token(db, tutor_id)
    if not token:
        raise GoogleApiError("Google: календарь не подключён.")
    try:
        return action(token)
    except GoogleUnauthorized:
        pass
    fresh = connection.force_refresh(db, tutor_id)
    if not fresh:
        raise GoogleApiError("Google: календарь не подключён.")
    return action(fresh)

def _handle_reauth(db: Session, tutor_id: str) -> None:
    """Сбрасывает подключение при отозванном доступе и пишет причину."""
    logger.warning("Google Календарь: доступ отозван (tutor=%s)", tutor_id)
    connection.clear(db, tutor_id)
    connection.set_last_error(db, tutor_id, REAUTH_HINT)

def log_failure(db: Session, tutor_id: str, exc: GoogleApiError) -> None:
    """Пишет ошибку в лог и в карточку; исключение не пробрасывается."""
    logger.warning("Google Календарь: %s (tutor=%s)", exc, tutor_id)
    try:
        connection.set_last_error(db, tutor_id, str(exc))
    except Exception:  # noqa: BLE001 — запись подсказки не должна ронять запрос
        logger.exception("Google Календарь: не удалось сохранить текст ошибки")
