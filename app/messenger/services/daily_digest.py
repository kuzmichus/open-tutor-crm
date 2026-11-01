"""Дневная сводка уроков в мессенджеры — задание cron.

Репетитор включает «Дневную сводку» на вкладке «Уведомления» и задаёт
время: в этот час (и позже, если прогон был пропущен) во все привязанные
каналы уходит список уроков текущего дня — время, имя ученика или группы
и пометка, если на счету ребёнка не хватает денег на урок.

```
есть привязанный чат?  ──нет──> пропустить
сводка включена?       ──нет──> пропустить
местное время >= digest_time? ──нет──> пропустить
маркер дня уже сегодня?       ──да──> пропустить
уроки дня есть?       ──нет──> поставить маркер, ничего не отправлять
иначе: текст → каждый привязанный канал → маркер дня
```

Идемпотентность — от маркера `digest_sent_date` в `tutor_params`: он
хранит локальную дату последней сводки, поэтому минутные прогоны и их
наложение не отправляют сводку дважды. Маркер ставится и после неудачной
попытки (ошибки каналов остаются в журнале `sent_messages`): иначе
сбойный канал ретраился бы каждую минуту до конца дня.

Пустых сводок не бывает: день без уроков — день без сообщения (правило
проекта «не показывать нули»). Пометка о нехватке средств включается
флагом `notify_insufficient_funds` — его описание на вкладке описывает
ровно этот сценарий.

Сервис не знает про FastAPI: на вход — сессия, на выход — число
отправленных сводок (для строки лога runner'а).
"""

import logging
from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import tutor_zone
from app.finance.services.balance import balance, shortfall
from app.finance.services.presentation import balance_label, money
from app.lesson.services.daily_digest import DigestLesson, DigestTarget, digest_lessons
from app.lesson.services.presentation import format_lesson_date
from app.messenger.services.binding import bound_chats, chat_id_key
from app.messenger.services.messengers import SUPPORTED
from app.messenger.services.send import send_message
from app.tutor.models.tutor import Tutor
from app.tutor.models.tutor_param import TutorParam
from app.tutor.services.clock import as_utc, utcnow
from app.tutor.services.params import get_param, set_param
from app.tutor.services.settings import get_settings

logger = logging.getLogger("cron")

# KV-параметр с датой последней отправленной сводки (ISO `YYYY-MM-DD`).
# Отдельная строка, а не колонка: миграция не нужна, ключ читается только
# этим заданием.
DIGEST_SENT_KEY = "digest_sent_date"

# Лимит Telegram — 4096 символов; обрезаем с запасом, чтобы многоточие и
# служебная разметка гарантированно влезли.
MAX_TEXT_LENGTH = 4000

_ELLIPSIS = "…"

# Заголовок сводки: «Сводка уроков на 01.11.2026».
TITLE = "Сводка уроков на {date}"


def _parse_digest_time(value: str | None) -> time | None:
    """«ЧЧ:ММ» из настроек → `time`; мусор в строке — None (сводку пропускаем).

    Значение пишет форма с валидацией, но строка могла остаться от старой
    версии или правки в обход формы: падать из-за неё cron не должен.
    """
    try:
        hours, minutes = (value or "").split(":")
        return time(int(hours), int(minutes))
    except (AttributeError, TypeError, ValueError):
        return None


def _shortfall_line(target: DigestTarget, balance_value: int) -> str:
    """Подстрока «не хватает N ₽ (на счету B ₽, урок P ₽)» или пустая строка.

    Сумма нехватки считается единственной формулой модуля finance
    (`balance.shortfall`), формат денег берётся оттуда же: числа в сводке
    и в счёте ученика должны читаться одинаково.
    """
    missing = shortfall(balance_value, target.price)
    if missing <= 0:
        return ""
    return (
        f"не хватает {money(missing)} "
        f"(на счету {balance_label(balance_value)}, урок {money(target.price)})"
    )


def _lesson_lines(lesson: DigestLesson, balances: dict[str, int], *, with_shortfall: bool) -> list[str]:
    """Строки одного урока: «ЧЧ:ММ — цель» и пометки о нехватке средств.

    Время — настенное время педагога: момент урока уже переведён в зону
    (`to_local`) вызывающим кодом, здесь только формат «ЧЧ:ММ».
    """
    head = f"{lesson.starts_at.strftime('%H:%M')} — {lesson.target_name}"
    lines = [head]
    if not with_shortfall:
        return lines
    for target in lesson.targets:
        note = _shortfall_line(target, balances[target.student_id])
        if not note:
            continue
        # В группе участников несколько — подстрока начинается с имени,
        # иначе непонятно, о ком речь.
        lines.append(f"  {target.name}: {note}" if lesson.is_group else f"  {note}")
    return lines


def build_digest_text(
    lessons: list[DigestLesson],
    tutor,
    *,
    balances: dict[str, int],
    with_shortfall: bool = True,
) -> str:
    """Текст сводки дня: заголовок с датой и строки уроков по порядку.

    Чистая функция форматирования (балансы приходят готовыми): так текст
    проверяется тестами без базы и без сети. Дата берётся у первого урока
    в зоне педагога — все уроки сводки принадлежат одному дню.
    """
    if not lessons:
        return ""
    header = TITLE.format(date=format_lesson_date(lessons[0].starts_at, tutor))
    body: list[str] = []
    for lesson in lessons:
        body.extend(_lesson_lines(lesson, balances, with_shortfall=with_shortfall))
    text = "\n".join([header, "", *body])
    if len(text) > MAX_TEXT_LENGTH:
        text = text[: MAX_TEXT_LENGTH - len(_ELLIPSIS)].rstrip() + _ELLIPSIS
    return text


def _balances(db: Session, lessons: list[DigestLesson]) -> dict[str, int]:
    """Балансы всех учеников дня: один расчёт на ученика, а не на урок."""
    ids = {target.student_id for lesson in lessons for target in lesson.targets}
    return {student_id: balance(db, student_id) for student_id in ids}


def _tutors_with_channels(db: Session) -> list[str]:
    """Id репетиторов, у которых привязан хотя бы один канал уведомлений."""
    keys = [chat_id_key(messenger) for messenger in SUPPORTED]
    return list(
        db.scalars(
            select(TutorParam.tutor_id)
            .where(TutorParam.key.in_(keys))
            .distinct()
            .order_by(TutorParam.tutor_id)
        ).all()
    )


def _send_digest(db: Session, tutor: Tutor, now_local: datetime) -> bool:
    """Отправляет сводку одному репетитору; True — сообщение ушло.

    Решение «слать или нет» принимается здесь целиком: флаг настроек,
    время, маркер дня. Маркер ставится при любом исходе после проверки
    времени — день считается обработанным, даже если уроков нет.
    """
    settings = get_settings(db, tutor.id)
    if not settings.notify_daily_digest:
        return False
    digest_time = _parse_digest_time(settings.digest_time)
    if digest_time is None:
        logger.warning("дневная сводка: некорректное время %r", settings.digest_time)
        return False
    if now_local.time() < digest_time:
        return False

    today = now_local.date()
    if get_param(db, tutor.id, DIGEST_SENT_KEY) == today.isoformat():
        return False

    chats = bound_chats(db, tutor.id)
    if not chats:
        return False

    lessons = digest_lessons(db, tutor, today)
    if lessons:
        # Момент урока переводим в зону педагога один раз, на входе в текст.
        lessons = [
            DigestLesson(
                starts_at=lesson.starts_at.astimezone(tutor_zone(tutor)),
                target_name=lesson.target_name,
                is_group=lesson.is_group,
                targets=lesson.targets,
            )
            for lesson in lessons
        ]
        text = build_digest_text(
            lessons,
            tutor,
            balances=_balances(db, lessons),
            with_shortfall=settings.notify_insufficient_funds,
        )
        for messenger, chat_id in chats.items():
            # Ошибка одного канала не мешает остальным: она уже в журнале
            # `sent_messages`, а сводку всё равно получит второй мессенджер.
            errors = send_message(db, tutor.id, messenger, chat_id, text)
            if errors:
                logger.warning(
                    "дневная сводка: %s не доставлена (%s)", messenger, errors[0]
                )

    set_param(db, tutor.id, DIGEST_SENT_KEY, today.isoformat())
    return bool(lessons)


def run_daily_digests(db: Session, *, now: datetime | None = None) -> int:
    """Отправляет сводки всем, кому пора; возвращает число отправленных.

    `now` — момент проверки (aware UTC); в тестах подменяется, в бою —
    `utcnow()`. Коммит после каждого репетитора: сетевые вызовы не должны
    держать открытую транзакцию SQLite и блокировать запись веб-приложению.
    """
    moment = as_utc(now or utcnow())
    sent = 0
    for tutor_id in _tutors_with_channels(db):
        tutor = db.get(Tutor, tutor_id)
        if tutor is None:  # pragma: no cover — FK CASCADE: строка не может пропасть
            continue
        if _send_digest(db, tutor, moment.astimezone(tutor_zone(tutor))):
            sent += 1
        db.commit()
    return sent
