"""Счёт за период: занятия периода, стоимость и текст сообщения (design D13).

Счёт — не документ и не операция: он ничего не сохраняет и не меняет
баланс. Это расчёт «сколько стоит следующий месяц» плюс готовый текст,
который репетитор копирует и отправляет ученику сам (отправка в
мессенджеры — Non-Goal change'а).

Правила:

- период по умолчанию — следующий календарный месяц;
- в список занятий попадает урок с определимой ценой: индивидуальный —
  `lesson.price`, групповой — цена участника (`price_override`) или общая
  цена группы. Урок без цены в счёт не попадает вовсе: «0 ₽» в счёте
  выглядел бы как бесплатное занятие;
- «Учесть остатки на балансе» — вычитание баланса из стоимости занятий:
  `К оплате = Стоимость занятий − Баланс`. Выключенный тумблер оставляет
  стоимость как есть.

Границы периода считаются в зоне педагога и переводятся в UTC (как неделя
календаря): иначе занятие вечером 30-го числа попало бы в чужой месяц.

Сервис не знает про FastAPI: на вход — сессия, ученик, репетитор и даты,
на выход — контекст шаблона.
"""

from calendar import monthrange
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, to_local, today_local
from app.finance.services.balance import balance
from app.finance.services.presentation import money
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson

# Подписи занятия в счёте: у урока нет предмета, поэтому строка называется
# «Урок»; для группового важно, что он групповой (цена — за человека).
INVOICE_LESSON_LABEL = "Урок"
INVOICE_GROUP_LABEL = "Групповой урок"


def next_month_period(tutor) -> tuple[date, date]:
    """Первый и последний день следующего календарного месяца в зоне педагога.

    Период по умолчанию — следующий месяц (спека student-finance, «Счёт за
    период»): репетитор выставляет счёт заранее, а не за уже прошедший.
    """
    today = today_local(tutor)
    if today.month == 12:
        year, month = today.year + 1, 1
    else:
        year, month = today.year, today.month + 1
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def parse_period(
    from_raw: str | None, to_raw: str | None, tutor
) -> tuple[date, date, list[str]]:
    """Период из query-параметров; пустое или неверное — период по умолчанию.

    Неверная дата не должна превращаться в 500: диалог открывается по
    ссылке, и опечатка в URL — не повод не показать счёт. Пользователь
    видит сообщение и период по умолчанию.
    """
    default_from, default_to = next_month_period(tutor)
    errors: list[str] = []

    start = _parse_day(from_raw)
    if start is None:
        if from_raw:
            errors.append("Дата начала указана неверно — показан следующий месяц.")
        start = default_from

    end = _parse_day(to_raw)
    if end is None:
        if to_raw:
            errors.append("Дата окончания указана неверно — показан следующий месяц.")
        end = default_to

    if start > end:
        errors.append("Дата начала позже даты окончания — показан следующий месяц.")
        return default_from, default_to, errors

    return start, end, errors


def _parse_day(value: str | None) -> date | None:
    """`YYYY-MM-DD` из query; пусто или мусор — `None`."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def priced_lessons(
    db: Session, student_id: str, start: date, end: date, tutor
) -> list[dict]:
    """Занятия периода с ценой, от ранних к поздним.

    Два `SELECT` вместо одного `UNION`: у индивидуального урока цена в
    `lesson.price`, у группового — в участнике и группе. Объединять их в
    SQL пришлось бы через `COALESCE` и внешние соединения, а правило цены
    уже живёт в `charges` — здесь оно повторяет его для чтения.

    Статус урока не важен: счёт за будущий месяц состоит из
    «Запланированных», за прошедший — из того, что было (design D13).
    """
    start_at, _ = local_day_bounds(start, tutor)
    _, end_at = local_day_bounds(end, tutor)

    rows: list[dict] = []

    individual = db.scalars(
        select(Lesson).where(
            Lesson.student_id == student_id,
            Lesson.price.is_not(None),
            Lesson.starts_at >= start_at,
            Lesson.starts_at < end_at,
        )
    ).all()
    for lesson in individual:
        rows.append(_line(lesson, lesson.price, tutor))

    group_rows = db.execute(
        select(Lesson, Group, GroupMember.price_override)
        .join(GroupMember, GroupMember.group_id == Lesson.group_id)
        .join(Group, Group.id == Lesson.group_id)
        .where(
            GroupMember.student_id == student_id,
            Lesson.starts_at >= start_at,
            Lesson.starts_at < end_at,
        )
    ).all()
    for lesson, group, price_override in group_rows:
        price = price_override if price_override is not None else group.price_per_lesson
        if price is None:
            continue
        rows.append(_line(lesson, price, tutor, group=group))

    rows.sort(key=lambda row: row["starts_at"])
    return rows


def _line(lesson: Lesson, price: int, tutor, *, group=None) -> dict:
    """Строка занятия: начало в зоне педагога, подпись и цена."""
    return {
        "starts_at": lesson.starts_at,
        "local": to_local(lesson.starts_at, tutor),
        "label": INVOICE_GROUP_LABEL if group is not None else INVOICE_LESSON_LABEL,
        "price": price,
    }


def invoice_text(
    start: date,
    end: date,
    lines: list[dict],
    total: int,
    balance_value: int,
    due: int,
    use_balance: bool,
) -> str:
    """Текст сообщения ученику: занятия, стоимость, баланс и сумма к оплате.

    Собирается на сервере, а не в JS: сумма к оплате уже посчитана
    сервисом, и клиент не должен повторять формулу ради текста.
    """
    header = f"Счёт за занятия {start:%d.%m.%Y}–{end:%d.%m.%Y}"
    parts = ["Здравствуйте!", "", header, ""]
    if lines:
        for line in lines:
            parts.append(
                f"{line['local']:%d.%m.%Y, %H:%M} — {line['label']} — "
                f"{money(line['price'])}"
            )
        parts.append("")
        parts.append(f"Занятий: {len(lines)}")
        parts.append(f"Стоимость занятий: {money(total)}")
        if use_balance:
            parts.append(f"Баланс ученика: {money(balance_value)}")
        parts.append(f"К оплате: {money(due)}")
    else:
        parts.append("Занятий в периоде нет.")
    parts.append("")
    return "\n".join(parts)


def invoice_context(
    db: Session,
    student,
    tutor,
    *,
    from_raw: str | None = None,
    to_raw: str | None = None,
    use_balance: bool = True,
) -> dict:
    """Контекст `finance/_invoice_dialog.html`: период, строки и сумма.

    Ничего не пишет в БД: открытие и закрытие счёта не меняют ни баланс,
    ни платежи, ни историю (спека student-finance, «Счёт не меняет счёт
    ученика»).
    """
    start, end, errors = parse_period(from_raw, to_raw, tutor)
    lines = priced_lessons(db, student.id, start, end, tutor)
    total = sum(line["price"] for line in lines)
    balance_value = balance(db, student.id)
    due = total - balance_value if use_balance else total

    return {
        "invoice_student": student,
        "invoice_lines": lines,
        "invoice_errors": errors,
        "invoice_from": start.isoformat(),
        "invoice_to": end.isoformat(),
        "invoice_from_label": f"{start:%d.%m.%Y}",
        "invoice_to_label": f"{end:%d.%m.%Y}",
        "invoice_total": total,
        "invoice_balance": balance_value,
        "invoice_due": due,
        "invoice_use_balance": use_balance,
        "invoice_text": invoice_text(
            start,
            end,
            lines,
            total,
            balance_value,
            due,
            use_balance,
        ),
    }
