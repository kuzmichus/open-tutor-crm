"""Метрики списка учеников: баланс, проведено, следующий урок, оплата.

Один набор агрегатов на весь список (design D1 change'а student-list-reference):
карточек у репетитора десятки, и запрос на каждую карточку был бы N+1. Все
выборки группируются по `student_id` и складываются в словари, которые
`attach_metrics` раздаёт карточкам.

Правила денег не дублируются: знак баланса выводит `balance.signed_amount`
(единственная формула D3 в проекте), а формат строки — `money()`/
`balance_label()` из `finance.presentation`, уже зарегистрированные шаблону.

Момент «сейчас» передаётся снаружи (`now`): у страницы и у модалок одного
запроса не должно расходиться, что уже «прошло» (тот же приём, что в
`lesson/services/lessons.py`).
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.finance.models.account_operation import (
    BALANCE_PAYMENT_STATUS,
    AccountOperation,
)
from app.finance.services.balance import signed_amount
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.tutor.services.clock import as_utc

# Ключи карточки, которые досчитывает `attach_metrics`.
BALANCE = "balance"
COMPLETED = "completed_count"
NEXT_AT = "next_lesson_at"
FIRST_PAYMENT = "first_payment_at"
LAST_PRICE = "last_price"
REMAINING = "remaining_lessons"


def _balances(db: Session, student_ids: list[str]) -> dict[str, int]:
    """Баланс по каждому ученику: GROUP BY «вид, статус» + формула знака.

    Сумма берётся агрегатом `SUM`, а не «сырой» колонкой: при `GROUP BY`
    без агрегата SQLite отдаёт произвольную строку группы, и баланс ученика
    с десятью уроками по 2 000 ₽ выглядел бы как 2 000 ₽, а не 20 000 ₽ —
    должник в списке числился бы платёжеспособным. Формула знака остаётся
    общей (`signed_amount`), агрегат её не дублирует: знак зависит только
    от «вид, статус», то есть от ключа группировки.
    """
    if not student_ids:
        return {}
    rows = db.execute(
        select(
            AccountOperation.student_id,
            AccountOperation.kind,
            AccountOperation.status,
            func.sum(AccountOperation.amount),
        )
        .where(AccountOperation.student_id.in_(student_ids))
        .group_by(
            AccountOperation.student_id,
            AccountOperation.kind,
            AccountOperation.status,
        )
    ).all()
    totals: dict[str, int] = {student_id: 0 for student_id in student_ids}
    for student_id, kind, status, total in rows:
        totals[student_id] += signed_amount(kind, status, int(total or 0))
    return totals


def _completed_counts(db: Session, student_ids: list[str]) -> dict[str, int]:
    """Число проведённых уроков: индивидуальные плюс групповые, где участник."""
    if not student_ids:
        return {}
    counts: dict[str, int] = {student_id: 0 for student_id in student_ids}

    individual = db.execute(
        select(Lesson.student_id, Lesson.id)
        .where(
            Lesson.student_id.in_(student_ids),
            Lesson.status == "completed",
        )
    ).all()
    for student_id, _lesson_id in individual:
        counts[student_id] += 1

    # Групповые уроки считаются через состав групп: у участника нет своей
    # строки в `lessons`, но занятие для него проведено так же.
    grouped = db.execute(
        select(GroupMember.student_id, Lesson.id)
        .join(Lesson, Lesson.group_id == GroupMember.group_id)
        .where(
            GroupMember.student_id.in_(student_ids),
            Lesson.status == "completed",
        )
    ).all()
    for student_id, _lesson_id in grouped:
        counts[student_id] += 1
    return counts


def _next_lessons(db: Session, student_ids: list[str], now: datetime) -> dict[str, datetime]:
    """Ближайший запланированный урок каждого ученика (UTC, `>= now`)."""
    if not student_ids:
        return {}
    result: dict[str, datetime] = {}

    individual = db.execute(
        select(Lesson.student_id, Lesson.starts_at)
        .where(
            Lesson.student_id.in_(student_ids),
            Lesson.status == "planned",
            Lesson.starts_at >= now,
        )
    ).all()
    for student_id, starts_at in individual:
        _keep_min(result, student_id, as_utc(starts_at))

    grouped = db.execute(
        select(GroupMember.student_id, Lesson.starts_at)
        .join(Lesson, Lesson.group_id == GroupMember.group_id)
        .where(
            GroupMember.student_id.in_(student_ids),
            Lesson.status == "planned",
            Lesson.starts_at >= now,
        )
    ).all()
    for student_id, starts_at in grouped:
        _keep_min(result, student_id, as_utc(starts_at))
    return result


def _keep_min(target: dict[str, datetime], student_id: str, value: datetime) -> None:
    """Минимум «ближайшего» урока: групповые и индивидуальные в одной куче."""
    current = target.get(student_id)
    if current is None or value < current:
        target[student_id] = value


def _first_payments(db: Session, student_ids: list[str]) -> dict[str, datetime]:
    """Дата первой оплаты: минимум `occurred_at` оплаченных платежей."""
    if not student_ids:
        return {}
    rows = db.execute(
        select(
            AccountOperation.student_id,
            AccountOperation.occurred_at,
        ).where(
            AccountOperation.student_id.in_(student_ids),
            AccountOperation.kind == "payment",
            AccountOperation.status == BALANCE_PAYMENT_STATUS,
        )
    ).all()
    result: dict[str, datetime] = {}
    for student_id, occurred_at in rows:
        _keep_min(result, student_id, as_utc(occurred_at))
    return result


def last_prices(db: Session, student_ids: list[str]) -> dict[str, int]:
    """Последняя известная цена ученика: свежий индивидуальный урок с ценой.

    «Осталось занятий» считается от этой цены. Групповые уроки намеренно не
    участвуют: их цена — свойство участника и группы, и брать её для
    прогноза остатка без контекста группы было бы догадкой. Публичная:
    тот же правило нужно отчёту за месяц (`report.py`) — вторая копия
    правила сделала бы остаток на карточке и в отчёте разным.
    """
    if not student_ids:
        return {}
    rows = db.execute(
        select(Lesson.student_id, Lesson.starts_at, Lesson.price)
        .where(
            Lesson.student_id.in_(student_ids),
            Lesson.price.is_not(None),
        )
        .order_by(Lesson.starts_at.desc(), Lesson.id.desc())
    ).all()
    prices: dict[str, int] = {}
    for student_id, _starts_at, price in rows:
        # Строки уже отсортированы: первая попавшаяся — самая свежая.
        if student_id not in prices:
            prices[student_id] = price
    return prices


def attach_metrics(
    db: Session,
    cards: list[dict],
    *,
    now: datetime,
) -> list[dict]:
    """Досчитывает метрики карточкам `build_cards` (мутирует и возвращает их).

    Ученик без операций и уроков получает честные нули/`None`: «0 ₽» здесь
    — настоящее число, потому что операций действительно нет (в отличие от
    прежней заглушки, нули которой были выдумкой).
    """
    student_ids = [card["student"].id for card in cards]
    balances = _balances(db, student_ids)
    completed = _completed_counts(db, student_ids)
    next_lessons = _next_lessons(db, student_ids, now)
    first_payments = _first_payments(db, student_ids)
    last_prices_map = last_prices(db, student_ids)

    for card in cards:
        student_id = card["student"].id
        balance = balances.get(student_id, 0)
        price = last_prices_map.get(student_id)
        card[BALANCE] = balance
        card[COMPLETED] = completed.get(student_id, 0)
        card[NEXT_AT] = next_lessons.get(student_id)
        card[FIRST_PAYMENT] = first_payments.get(student_id)
        card[LAST_PRICE] = price
        # Остаток занятий имеет смысл только при положительном балансе и
        # известной цене: иначе «0 занятий» читалось бы как «бесплатно».
        card[REMAINING] = (
            balance // price if balance > 0 and price and price > 0 else None
        )
    return cards


def attach_card_metrics(db: Session, card: dict, *, now: datetime) -> dict:
    """Метрики одной карточки — для ответов «создать/править/архив».

    Эти вьюхи возвращают `_card.html` вместо всей сетки: карточка обязана
    прийти с тем же набором полей, что и в списке, иначе вставка в сетку
    рендерилась бы без баланса и метрик.
    """
    return attach_metrics(db, [card], now=now)[0]


def debt_summary(cards: list[dict]) -> dict | None:
    """Сводка долга по видимому списку; должников нет — `None`.

    Считается по уже отфильтрованным карточкам (design D2): числа панели
    не могут разойтись с карточками ниже.
    """
    debtors = [card for card in cards if card.get(BALANCE, 0) < 0]
    if not debtors:
        return None
    return {
        "total": -sum(card[BALANCE] for card in debtors),
        "count": len(debtors),
    }
