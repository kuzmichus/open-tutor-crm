"""Вкладка «Прогноз на месяц»: сколько репетитор заработает к концу месяца.

Прогноз строится из трёх источников, и каждый отвечает на свой вопрос:

- **Факт** — уже списанные деньги: суммы списаний за проведённые уроки
  месяца (`kind='lesson'`). Это состоявшаяся выручка, её не прогнозируют.
- **По календарю** — запланированные уроки от «сейчас» до конца месяца
  с их ценами. Цена группового урока — сумма цен участников (их
  индивидуальная цена либо общая цена группы): выручка репетитора — это
  то, что спишется с учеников.
- **Не в расписании** — ученики, которые занимались за последние четыре
  недели, но в календаре на остаток месяца у них нет ни одного занятия.
  Такие ученики обычно продолжают ходить, просто договорённость не
  занесена: ожидаемое число занятий — их же темп за четыре недели,
  умноженный на оставшиеся недели, по их обычной цене.

Диапазон «Итого за месяц» получается сам: нижняя граница — факт плюс
календарь (запланированное точно состоится), верхняя — плюс ожидание
вне расписания. Отдельного «коэффициента отмен» в модели нет: статусов
отмены у урока не существует (`LESSON_STATUSES`), и выдумывать его из
воздуха значило бы показывать репетитору число без источника.

«Деньги к поступлению» — сколько ещё внесут ученики: будущие списания
(календарь плюс ожидание вне расписания) за вычетом предоплаты, уже
лежащей на балансах учеников. Факт сюда не входит — эти деньги уже
списаны с балансов.

Прогноз по педагогам, зарплату и маржу вкладка не считает: у репетитора
один аккаунт, а ставки педагогов в модели нет — числа были бы нулями
(осознанное решение владельца).

Сервис не знает про FastAPI: на вход — сессия, репетитор и месяц,
на выход — контекст для `finance/_forecast.html`.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import (
    local_day_bounds,
    now_local,
    now_utc,
    today_local,
    to_local,
    tutor_zone,
)
from app.finance.models.account_operation import AccountOperation
from app.finance.models.forecast_snapshot import ForecastSnapshot
from app.finance.services.balances import student_balances
from app.finance.services.presentation import MINUS, lessons_count_label, money
from app.group.models.group import Group
from app.group.models.group_member import GroupMember
from app.lesson.models.lesson import Lesson
from app.student.models.student import Student

# Месяцы прогноза: текущий и следующий. Прошлое прогнозировать незачем —
# оно уже факт; дальше следующего месяца цены и состав групп слишком
# подвижны, чтобы число что-то значило.
MONTH_OPTIONS = ("current", "next")

# Окно наблюдения за занятиями «вне расписания»: четыре недели — тот же
# горизонт, что у референса («за 4 недели N зан.»).
UNSCHEDULED_WINDOW_DAYS = 28
UNSCHEDULED_WINDOW_WEEKS = UNSCHEDULED_WINDOW_DAYS / 7
UNSCHEDULED_WINDOW_LABEL = "за 4 недели"

# Подписи вариантов селектора месяца.
MONTH_TITLES = {"current": "Текущий", "next": "Следующий"}

# Названия месяцев в именительном падеже: «Октябрь 2026» в подписи месяца
# и «за октябрь 2026» в пояснении карточки «Факт» (винительный совпадает
# с именительным у всех двенадцати).
_MONTHS = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)

# Короткая подпись снимка: «26.10, 02:04».
_SNAPSHOT_FORMAT = "%d.%m, %H:%M"


def parse_forecast_month(params, tutor) -> dict:
    """Месяц прогноза из query; мусор и опечатки — текущий месяц.

    Возвращает ключ выбора, границы окна `[start, end)` в UTC и локальный
    конец месяца (по нему считается, сколько недель осталось).
    """
    key = params.get("month", MONTH_OPTIONS[0])
    if key not in MONTH_OPTIONS:
        key = MONTH_OPTIONS[0]

    today = today_local(tutor)
    year, month = today.year, today.month
    if key == "next":
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    first = date(year, month, 1)
    after = (first + timedelta(days=32)).replace(day=1)
    return {
        "key": key,
        "year": year,
        "month": month,
        "label": f"{_MONTHS[month - 1]} {year}",
        "start": local_day_bounds(first, tutor)[0],
        "end": local_day_bounds(after, tutor)[0],
        "local_end": datetime.combine(after, time.min).replace(
            tzinfo=tutor_zone(tutor)
        ),
    }


def month_options(tutor) -> list[dict]:
    """Варианты селектора месяца: «Текущий: Октябрь 2026» и следующий."""
    return [
        {
            "key": key,
            "label": (
                f"{MONTH_TITLES[key]}: "
                f"{parse_forecast_month({'month': key}, tutor)['label']}"
            ),
        }
        for key in MONTH_OPTIONS
    ]


def range_label(low: int, high: int) -> str:
    """Диапазон сумм: «9 720 ₽ – 9 974 ₽» (равные границы тоже диапазон).

    Референс показывает диапазон и у величины без разброса («3 600 ₽ –
    3 600 ₽»): карточки читаются в одном формате, глаз не спотыкается
    о смену вида числа.
    """
    return f"{money(low)} \u2013 {money(high)}"


def _percent(value: float) -> str:
    """«37,8» — доля с одним знаком и запятой, как в русском счёте."""
    return f"{value:.1f}".replace(".", ",")


def students_label(count: int) -> str:
    """«1 ученик» / «2 ученика» / «5 учеников» — русская плюрализация.

    Исключения на «-надцать» (11–14) идут первыми: у них окончание
    «учеников», хотя последняя цифра — 1–4.
    """
    if count % 100 in (11, 12, 13, 14):
        return f"{count} учеников"
    if count % 10 == 1:
        return f"{count} ученик"
    if count % 10 in (2, 3, 4):
        return f"{count} ученика"
    return f"{count} учеников"


def _lesson_charges(db: Session, tutor_id: str, *, start, end) -> list[dict]:
    """Списания за проведённые уроки окна: строки с учеником и суммой."""
    rows = db.execute(
        select(
            AccountOperation.student_id,
            AccountOperation.amount,
            AccountOperation.occurred_at,
            Student.first_name,
            Student.last_name,
            Student.status,
        )
        .join(Student, Student.id == AccountOperation.student_id)
        .where(
            Student.tutor_id == tutor_id,
            AccountOperation.kind == "lesson",
            AccountOperation.occurred_at >= start,
            AccountOperation.occurred_at < end,
        )
        .order_by(AccountOperation.occurred_at)
    ).all()
    return [
        {
            "student_id": student_id,
            "amount": amount,
            "occurred_at": occurred_at,
            "name": " ".join(part for part in (first, last) if part) or "Без имени",
            "student_status": status,
        }
        for student_id, amount, occurred_at, first, last, status in rows
    ]


def _planned_targets(
    db: Session, tutor_id: str, *, start, end
) -> tuple[list[dict], int, int]:
    """Запланированные уроки окна: пары «ученик, цена», уроки без цены, оплаченные уроки.

    Групповой урок даёт по строке на участника: выручка репетитора — сумма
    списаний, а списание создаётся каждому участнику по его цене
    (`charges.lesson_targets`). Цена участника — индивидуальная
    (`price_override`), иначе общая цена группы.

    Урок без определимой цены в сумму не входит и считается отдельно —
    о нём говорит блок предупреждений. Группа без цен у всех участников —
    тоже «урок без цены».

    Третий результат — число уроков, которые дали хоть одну цену: у
    группового занятия участников трое, а занятие одно, и подпись «N
    занятий до конца месяца» не должна считать уроки, которых нет в сумме.
    """
    individual = db.execute(
        select(
            Lesson.id,
            Lesson.price,
            Student.id,
            Student.first_name,
            Student.last_name,
        )
        .join(Student, Student.id == Lesson.student_id)
        .where(
            Student.tutor_id == tutor_id,
            Lesson.status == "planned",
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
    ).all()

    grouped = db.execute(
        select(Lesson.id, Lesson.group_id, Group.price_per_lesson)
        .join(Group, Group.id == Lesson.group_id)
        .where(
            Group.tutor_id == tutor_id,
            Lesson.status == "planned",
            Lesson.starts_at >= start,
            Lesson.starts_at < end,
        )
    ).all()

    # Состав групп — одним запросом на все группы окна (без N+1 на урок).
    members_by_group: dict[str, list] = {}
    group_ids = {group_id for _, group_id, _ in grouped}
    if group_ids:
        members = db.execute(
            select(
                GroupMember.group_id,
                GroupMember.price_override,
                Student.id,
                Student.first_name,
                Student.last_name,
            )
            .join(Student, Student.id == GroupMember.student_id)
            .where(GroupMember.group_id.in_(group_ids))
        ).all()
        for group_id, override, student_id, first, last in members:
            members_by_group.setdefault(group_id, []).append(
                (override, student_id, first, last)
            )

    rows: list[dict] = []
    unpriced = 0
    priced_lessons = 0
    for _, price, student_id, first, last in individual:
        if price is None:
            unpriced += 1
            continue
        priced_lessons += 1
        rows.append(_target(student_id, first, last, price))

    for _, group_id, group_price in grouped:
        priced = 0
        for override, student_id, first, last in members_by_group.get(group_id, ()):
            price = override if override is not None else group_price
            if price is None:
                continue
            priced += 1
            rows.append(_target(student_id, first, last, price))
        if priced == 0:
            unpriced += 1
        else:
            priced_lessons += 1

    return rows, unpriced, priced_lessons


def _target(student_id: str, first: str | None, last: str | None, price: int) -> dict:
    """Строка цели урока: ученик и его цена."""
    return {
        "student_id": student_id,
        "name": " ".join(part for part in (first, last) if part) or "Без имени",
        "price": price,
    }


def _group_by_student(targets: list[dict]) -> list[dict]:
    """Строки «ученик — сколько занятий и на какую сумму» по убыванию суммы."""
    totals: dict[str, dict] = {}
    for target in targets:
        row = totals.setdefault(
            target["student_id"],
            {
                "student_id": target["student_id"],
                "name": target["name"],
                "count": 0,
                "total": 0,
            },
        )
        row["count"] += 1
        row["total"] += target["price"]
    for row in totals.values():
        # Подписи собираются здесь: шаблон не склоняет и не форматирует сам.
        row["count_label"] = lessons_count_label(row["count"])
        row["total_label"] = money(row["total"])
    return sorted(totals.values(), key=lambda row: (-row["total"], row["name"]))


def _unscheduled(
    db: Session, tutor_id: str, tutor, *, month: dict, planned_students: set[str]
) -> tuple[list[dict], int]:
    """Ученики без плана на остаток месяца: ожидание по их темпу занятий.

    Темп — число списаний за последние четыре недели; цена — сумма
    последнего списания (текущая цена ученика, а не средняя по истории,
    где могли быть старые цены). Ожидаемое число занятий — темп,
    умноженный на оставшиеся недели месяца; оно дробное, поэтому и сумма
    округляется, а не берётся кратной цене урока.

    Ученики, у которых план на остаток месяца есть, сюда не попадают:
    их занятия уже посчитаны в «По календарю», второй раз считать нельзя.
    Архивные не попадают тоже: они больше не занимаются, ожидание по ним
    было бы выдумкой.
    """
    now = now_utc()
    window_start = now - timedelta(days=UNSCHEDULED_WINDOW_DAYS)
    recent = _lesson_charges(db, tutor_id, start=window_start, end=now)

    per_student: dict[str, dict] = {}
    for charge in recent:
        if charge["student_status"] != "active":
            continue
        row = per_student.setdefault(
            charge["student_id"],
            {
                "student_id": charge["student_id"],
                "name": charge["name"],
                "count": 0,
                "price": 0,
            },
        )
        row["count"] += 1
        # Строки отсортированы по occurred_at: последняя цена — текущая.
        row["price"] = charge["amount"]

    weeks_left = max(
        0.0, (month["local_end"] - now_local(tutor)).total_seconds() / (7 * 86400)
    )

    rows: list[dict] = []
    expected_lessons = 0.0
    for student_id, row in per_student.items():
        if student_id in planned_students:
            continue
        pace = row["count"] / UNSCHEDULED_WINDOW_WEEKS
        lessons = pace * weeks_left
        amount = round(row["price"] * lessons)
        if amount <= 0:
            continue
        expected_lessons += lessons
        rows.append(
            {
                "student_id": student_id,
                "name": row["name"],
                "detail": (
                    f"{UNSCHEDULED_WINDOW_LABEL} {row['count']} зан."
                    f" \u00b7 обычно {money(row['price'])}"
                ),
                "amount": money(amount),
                "amount_value": amount,
            }
        )

    rows.sort(key=lambda item: (-item["amount_value"], item["name"]))
    # Ожидаемое число занятий дробное (темп × неполные недели), а подпись
    # «ожидаем N занятий» — целая: округляем сумму, но у непустого списка
    # не показываем «0 занятий» — ожидание есть, раз есть строки.
    lessons_total = max(1, round(expected_lessons)) if rows else 0
    return rows, lessons_total


def _snapshot_card(db: Session, tutor, *, month: dict, fact: int) -> dict | None:
    """Карточка «Прогноз vs факт»: последний снимок месяца и отклонение факта.

    Отклонение считается от середины диапазона снимка: у прогноза две
    границы, и процент «ниже прогноза» от одной из них врал бы в пользу
    репетитора или против него. Снимка нет — карточки нет вовсе.
    """
    snapshot = db.scalars(
        select(ForecastSnapshot)
        .where(
            ForecastSnapshot.tutor_id == tutor.id,
            ForecastSnapshot.year == month["year"],
            ForecastSnapshot.month == month["month"],
        )
        .order_by(ForecastSnapshot.created_at.desc())
    ).first()
    if snapshot is None:
        return None

    middle = (snapshot.revenue_low + snapshot.revenue_high) / 2
    if fact < snapshot.revenue_low:
        status = "below"
    elif fact > snapshot.revenue_high:
        status = "above"
    else:
        status = "inrange"

    if status == "inrange" or middle <= 0:
        deviation = "в диапазоне"
    else:
        share = abs(fact - middle) / middle * 100
        sign = MINUS if status == "below" else "+"
        deviation = f"{sign}{_percent(share)} %"

    return {
        "captured_at": to_local(snapshot.created_at, tutor).strftime(_SNAPSHOT_FORMAT),
        "range": range_label(snapshot.revenue_low, snapshot.revenue_high),
        "fact": money(fact),
        "deviation": deviation,
        "status": status,
        "status_label": {
            "below": "ниже прогноза",
            "above": "выше прогноза",
            "inrange": "в диапазоне",
        }[status],
        "status_class": f"fin-snapshot__badge--{status}",
    }


def forecast_context(db: Session, tutor, *, month: dict) -> dict:
    """Контекст `finance/_forecast.html`: карточки, списки, снимок, предупреждения."""
    now = now_utc()
    charges = _lesson_charges(db, tutor.id, start=month["start"], end=month["end"])
    fact = sum(charge["amount"] for charge in charges)

    # Календарь — только будущее: проведённые уроки месяца уже в факте.
    planned, unpriced, planned_lessons = _planned_targets(
        db, tutor.id, start=max(month["start"], now), end=month["end"]
    )
    calendar_total = sum(row["price"] for row in planned)
    calendar_rows = _group_by_student(planned)
    planned_students = {row["student_id"] for row in planned}

    unscheduled_rows, expected_lessons = _unscheduled(
        db, tutor.id, tutor, month=month, planned_students=planned_students
    )
    unscheduled_total = sum(row["amount_value"] for row in unscheduled_rows)

    # Предоплата — положительные балансы учеников: эти деньги уже внесены
    # и закроют часть будущих списаний.
    prepayment = sum(
        row.balance for row in student_balances(db, tutor.id) if row.balance > 0
    )

    total_low = fact + calendar_total
    total_high = total_low + unscheduled_total
    # Предоплата закрывает часть будущих списаний: нижняя граница — то, что
    # внесут за календарь сверх балансов, верхняя — плюс ожидание вне
    # расписания. Отрицательной сумма не бывает: «к поступлению» не может
    # означать «к возврату».
    receive_low = max(0, calendar_total - prepayment)
    receive_high = receive_low + unscheduled_total

    cards = [
        {
            "key": "fact",
            "label": "Факт",
            "value": money(fact),
            "note": f"Уже списано за {month['label'].lower()}",
            "hint": "Сумма списаний за проведённые уроки этого месяца",
        },
        {
            "key": "calendar",
            "label": "По календарю",
            "value": range_label(calendar_total, calendar_total),
            "note": (
                f"{lessons_count_label(planned_lessons)} до конца месяца"
                if planned_lessons
                else "Запланированных уроков до конца месяца нет"
            ),
            "hint": "Запланированные уроки и их цены: сумма цен участников группы",
        },
        {
            "key": "unscheduled",
            "label": "Не в расписании",
            "value": money(unscheduled_total),
            "note": (
                f"{students_label(len(unscheduled_rows))} без занятий в календаре; "
                f"ожидаем {lessons_count_label(expected_lessons)}"
                if unscheduled_rows
                else "Все ученики с занятиями в календаре"
            ),
            "hint": (
                "Ученики, которые занимались последние четыре недели, но в "
                "календаре на остаток месяца их нет: ожидание по их темпу"
            ),
        },
        {
            "key": "total",
            "label": "Итого за месяц",
            "value": range_label(total_low, total_high),
            "note": "Факт + календарь + ожидание вне расписания",
            "hint": "Сколько репетитор заработает за месяц по текущим данным",
        },
        {
            "key": "receive",
            "label": "Деньги к поступлению",
            "value": range_label(receive_low, receive_high),
            "note": (
                "Сколько ещё внесут ученики до конца месяца; "
                f"предоплата на балансах: {money(prepayment)}"
            ),
            "hint": (
                "Будущие списания за вычетом предоплаты, уже лежащей на "
                "балансах учеников"
            ),
        },
    ]

    warnings = []
    if unpriced:
        warnings.append(
            f"{lessons_count_label(unpriced)} без цены не вошли в прогноз — "
            "задайте цену урока или группы."
        )

    return {
        "month": month,
        "month_options": month_options(tutor),
        "cards": cards,
        "warnings": warnings,
        "calendar_rows": calendar_rows,
        "unscheduled_rows": unscheduled_rows,
        "snapshot": _snapshot_card(db, tutor, month=month, fact=fact),
        "csv_url": f"/tutor/finance/forecast.csv?month={month['key']}",
        "fact": fact,
        "total_low": total_low,
        "total_high": total_high,
    }


def pin_forecast(db: Session, tutor, *, month: dict) -> ForecastSnapshot:
    """Фиксирует текущий прогноз месяца (заменяет прежний снимок).

    Повторная фиксация того же месяца обновляет строку, а не плодит новую:
    снимок — «последнее слово» репетитора о месяце, и карточка сравнения
    должна показывать именно его. Значения пересчитываются здесь же, а не
    берутся из формы: снимок обязан совпадать с тем, что видно на экране.
    """
    context = forecast_context(db, tutor, month=month)
    snapshot = db.scalars(
        select(ForecastSnapshot).where(
            ForecastSnapshot.tutor_id == tutor.id,
            ForecastSnapshot.year == month["year"],
            ForecastSnapshot.month == month["month"],
        )
    ).first()
    if snapshot is None:
        snapshot = ForecastSnapshot(
            tutor_id=tutor.id,
            year=month["year"],
            month=month["month"],
            revenue_low=context["total_low"],
            revenue_high=context["total_high"],
        )
        db.add(snapshot)
    else:
        snapshot.revenue_low = context["total_low"]
        snapshot.revenue_high = context["total_high"]
        snapshot.created_at = now_utc()
    db.commit()
    return snapshot


def forecast_csv(context: dict) -> str:
    """CSV прогноза: сводка, календарь и ожидание вне расписания.

    Разделитель — точка с запятой (русская локаль Excel), числа — без
    разделителей разрядов и без знака валюты: файл открывают в таблице,
    и «9 720 ₽» там стало бы текстом. BOM в начале — иначе Excel читает
    кириллицу как cp1251 и ломает имена учеников.
    """
    lines = [
        "Сводка;Нижняя граница;Верхняя граница",
        f"Месяц;{context['month']['label']};",
        f"Факт;{context['fact']};",
        f"Итого за месяц;{context['total_low']};{context['total_high']}",
    ]
    if context["snapshot"]:
        snapshot = context["snapshot"]
        lines.append(f"Прогноз на снимок;{snapshot['range']};")
        lines.append(f"Факт vs прогноз;{snapshot['deviation']};")

    lines.append("")
    lines.append("По ученикам — календарь;Занятий;Сумма")
    for row in context["calendar_rows"]:
        lines.append(f"{row['name']};{row['count']};{row['total']}")

    lines.append("")
    lines.append("Не в расписании;Ожидание;Сумма")
    for row in context["unscheduled_rows"]:
        lines.append(f"{row['name']};{row['detail']};{row['amount_value']}")

    return "\ufeff" + "\n".join(lines) + "\n"
