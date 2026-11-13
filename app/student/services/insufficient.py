"""Фильтр списка «кому не хватает денег на сегодняшние занятия».

Ссылка «Открыть» из плашки-напоминания ведёт сюда, а не в общий список
должников: плашка честно сообщает нехватку и у ученика с балансом 500 ₽
при цене занятия 2 000 ₽, а фильтр «должники» оставляет только
отрицательный баланс и такого ученика скрыл бы — пользователь увидел бы
пустой список вместо адресата напоминания.

Критерий не дублируется: состав учеников берётся из того же сервиса, что
считает саму плашку (`lesson.services.balance_notice`), поэтому список и
плашка не могут разойтись. Направление импорта `student → lesson` в
проекте уже есть (`list_metrics` знает модель урока).

Сервис не знает про FastAPI: на вход — сессия и карточка педагога, на
выход — набор id учеников и отфильтрованные карточки.
"""

from sqlalchemy.orm import Session

from app.lesson.services.balance_notice import today_balance_notice

# Имя query-параметра фильтра: `/tutor/students?shortfall=1`.
FILTER_PARAM = "shortfall"
FILTER_VALUE = "1"


def is_requested(value: str | None) -> bool:
    """Запрошен ли фильтр нехватки: значение query-параметра `shortfall`."""
    return value == FILTER_VALUE


def students_with_shortfall(db: Session, tutor) -> set[str]:
    """id учеников, которым не хватает денег на сегодняшние уроки.

    Пустой набор — показывать нечего: либо уроков на день нет, либо денег
    хватает. Тогда фильтр оставляет пустой список, а не весь.
    """
    notice = today_balance_notice(db, tutor)
    return set(notice["student_ids"]) if notice else set()


def filter_cards(cards: list[dict], student_ids: set[str]) -> list[dict]:
    """Оставляет карточки учеников из набора (карточки — словари `build_cards`)."""
    return [card for card in cards if card["student"].id in student_ids]
