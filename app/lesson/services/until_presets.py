"""Быстрые пресеты «До даты» панели расписания серии.

Значения берутся из настроек календаря репетитора (вкладка «Календарь»
профиля): даты окончания четвертей хранятся строками «ММ-ДД» без года
(design D6 change tutor-profile-settings), поэтому пресет подставляет
ближайшую будущую дату этого дня — «до конца II четв.» в мае означает
конец II четверти следующего учебного года, а не прошедшую дату.

Сервис не знает про FastAPI: на вход — сессия и карточка репетитора,
на выход — список пресетов для шаблона.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.common.services.tutor_time import to_local
from app.tutor.services.calendar_form import QUARTER_FIELDS
from app.tutor.services.clock import utcnow
from app.tutor.services.settings import get_settings

# Порядковые номера четвертей в подписи пресета — по порядку QUARTER_FIELDS.
_QUARTER_ORDINALS = ("I", "II", "III", "IV")


def _nearest_future(today: date, month_day: str) -> date | None:
    """Ближайшая будущая дата дня «ММ-ДД»: в этом году или в следующем.

    Дата, совпадающая с сегодняшним днём, остаётся как есть: «до конца
    четверти» в её последний день ещё имеет смысл. Разобрать «ММ-ДД»
    нельзя (нарушен формат в БД) — пресет пропускается, а не ломает форму.
    """
    try:
        month, day = (int(part) for part in month_day.split("-"))
        candidate = date(today.year, month, day)
    except (TypeError, ValueError):
        return None
    if candidate < today:
        try:
            candidate = date(today.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def until_presets(db: Session, tutor) -> list[dict]:
    """Пресеты «До даты» из настроек календаря репетитора.

    Каждая настроенная четверть превращается в чип «До конца N четв.»:
    клик подставляет вычисленную дату в поле «Дата окончания». День
    «сегодня» считается в зоне педагога — у репетитора в UTC+14 пресет
    не должен прыгать на прошлый день из-за серверной зоны.
    """
    settings = get_settings(db, tutor.id)
    today = to_local(utcnow(), tutor).date()

    presets: list[dict] = []
    for ordinal, field in zip(_QUARTER_ORDINALS, QUARTER_FIELDS):
        value = _nearest_future(today, getattr(settings, field))
        if value is None:
            continue
        presets.append(
            {
                "label": f"До конца {ordinal} четв.",
                "value": value.isoformat(),
                # Подсказка с конкретной датой: чип называет период,
                # а не дату — точное значение видно до клика.
                "title": value.strftime("%d.%m.%Y"),
            }
        )
    return presets
