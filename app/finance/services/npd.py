"""Налог на профессиональный доход (НПД) для страницы «Финансы».

Самозанятый платит с начисленного дохода две разные ставки: 4 % с денег
физлиц и 6 % с денег юрлиц. Признак плательщика живёт у ученика
(`students.payer_type`, задача TOCRM-42), ставки и годовой лимит — в
настройках профиля (`tutor_settings`), поэтому закон меняется без правки
кода: страница читает числа из настроек.

Правила расчёта (зафиксированы в openspec, change add-npd-tax-block):

- база — **начисленный** доход (`kind='lesson'`), а не касса: налог
  считается с выставленных счетов, даже если ученик ещё не заплатил;
- деньги — целые рубли, налог — `(доход × ставка + 5000) // 10000`
  (половина копейки вверх): сумма детализации всегда равна итогу, float
  в расчёте нет;
- годовой лимит считается по календарному году в зоне педагога, с 1
  января до «сейчас», и не зависит от выбранного периода сводки;
- при выключенном флаге `is_npd_payer` сервис не делает ни одного
  запроса и возвращает `{"enabled": False}`: страница выглядит как раньше.

Сервис не знает про FastAPI: на вход — сессия, репетитор и окно, на
выход — готовые словари для шаблона.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, today_local
from app.finance.models.account_operation import AccountOperation
from app.finance.services.presentation import money, npd_rate_label
from app.student.models.student import Student
from app.tutor.models.tutor_settings import NPD_LIMIT_WARN_PERCENT
from app.tutor.services.settings import get_settings

# Тип плательщика по умолчанию: ученики, созданные до TOCRM-42 или с
# неизвестным значением, считаются физлицами — ставка ниже, и это
# совпадает с прежним поведением формы.
PAYER_INDIVIDUAL = "individual"
PAYER_LEGAL = "legal_entity"

# Доля дохода от юрлиц, начиная с которой появляется подсказка про ставку
# 6 % (п. 4 ТЗ: «если юрлиц > 30-40 %», взята нижняя граница).
NPD_LEGAL_INSIGHT_PERCENT = 30

# Сноска блока: налог считает приложение «Мой налог», сумма расчётная.
NPD_NOTE = (
    "Налог рассчитывается автоматически в приложении «Мой налог». "
    "Сумма может быть уменьшена на остаток налогового вычета."
)


def _lesson_conditions(tutor_id: str, *, start, end) -> list:
    """Условия выборки начисленного дохода репетитора за окно.

    `kind='lesson'` — списания за проведённые уроки: налог считается с
    начислений, а не с пришедших платежей.
    """
    conditions = [Student.tutor_id == tutor_id, AccountOperation.kind == "lesson"]
    if start is not None:
        conditions.append(AccountOperation.occurred_at >= start)
    if end is not None:
        conditions.append(AccountOperation.occurred_at < end)
    return conditions


def earned_split(db: Session, tutor_id: str, *, start, end) -> dict[str, int]:
    """Начисленный доход периода по типу плательщика — одним запросом.

    Возвращает `{"individual": …, "legal_entity": …}`. `NULL` и значения
    вне закрытого списка относятся к физлицам: ставка ниже, и строка
    дохода не теряется — сумма половин всегда равна карточке «Доход».
    """
    rows = db.execute(
        select(Student.payer_type, func.sum(AccountOperation.amount))
        .join(Student, Student.id == AccountOperation.student_id)
        .where(*_lesson_conditions(tutor_id, start=start, end=end))
        .group_by(Student.payer_type)
    ).all()

    split = {PAYER_INDIVIDUAL: 0, PAYER_LEGAL: 0}
    for payer_type, total in rows:
        # Значение вне закрытого списка (старые данные, ручная правка БД)
        # считается физлицом: строка дохода не теряется.
        key = PAYER_LEGAL if payer_type == PAYER_LEGAL else PAYER_INDIVIDUAL
        split[key] += int(total or 0)
    return split


def tax_amount(income: int, basis_points: int) -> int:
    """Налог с суммы по ставке в базисных пунктах: целые рубли.

    `(доход × bp + 5000) // 10000` — округление половины вверх. Целые
    числа, а не float: сумма детализации обязана сходиться с итогом до
    рубля, а `0.04 * 20000` в двоичной дроби даёт 799.999…
    """
    return (income * basis_points + 5_000) // 10_000


def tax_context(split: dict[str, int], settings) -> dict:
    """Итог и детализация налога: числа и подписи ставок для шаблона."""
    individual_income = split.get(PAYER_INDIVIDUAL, 0)
    legal_income = split.get(PAYER_LEGAL, 0)
    rate_individual_bp = settings.npd_rate_individual_bp
    rate_legal_bp = settings.npd_rate_legal_bp
    individual_tax = tax_amount(individual_income, rate_individual_bp)
    legal_tax = tax_amount(legal_income, rate_legal_bp)
    return {
        "individual_income": individual_income,
        "legal_income": legal_income,
        "individual_tax": individual_tax,
        "legal_tax": legal_tax,
        "total": individual_tax + legal_tax,
        "rate_individual_bp": rate_individual_bp,
        "rate_legal_bp": rate_legal_bp,
        "individual_rate_label": npd_rate_label(rate_individual_bp),
        "legal_rate_label": npd_rate_label(rate_legal_bp),
    }


def ytd_income(db: Session, tutor) -> int:
    """Начисленный доход с 1 января текущего года до «сейчас».

    Лимит НПД — годовой, поэтому окно не зависит от периода сводки:
    «Этот месяц» и «Всё время» показывают один и тот же прогресс лимита.
    Границы — настенным временем педагога, как у периодов страницы.
    """
    today = today_local(tutor)
    start = local_day_bounds(date(today.year, 1, 1), tutor)[0]
    end = local_day_bounds(today, tutor)[1]

    stmt = (
        select(func.coalesce(func.sum(AccountOperation.amount), 0))
        .select_from(AccountOperation)
        .join(Student, Student.id == AccountOperation.student_id)
        .where(*_lesson_conditions(tutor.id, start=start, end=end))
    )
    return int(db.scalar(stmt) or 0)


def limit_context(income: int, limit: int) -> dict:
    """Прогресс годового лимита: проценты, ширина полосы, предупреждение.

    `percent` округляется половиной вверх целочисленно, `bar` зажат в
    0..100 (шкала не выезжает за край), `is_warning` включается на пороге
    из настроек (по умолчанию 80 %). Нулевой лимит не делит на ноль:
    форма не даёт его сохранить, guard — страховка от ручной правки БД.
    """
    percent = 0
    if limit > 0:
        percent = (income * 200 + limit) // (2 * limit)
    return {
        "income": income,
        "limit": limit,
        "percent": percent,
        "bar": min(100, max(0, percent)),
        "is_warning": percent >= NPD_LIMIT_WARN_PERCENT,
        "remaining": max(0, limit - income),
        "income_label": money(income),
        "limit_label": money(limit),
        "remaining_label": money(max(0, limit - income)),
    }


def legal_insight(
    split: dict[str, int], rate_individual_bp: int, rate_legal_bp: int
) -> str | None:
    """Совет про юрлиц: доля их дохода выше порога — ставка дороже.

    Сравниваются доли дохода, а не число учеников: совет про деньги,
    поэтому и вес — деньги. Ставки в тексте берутся из настроек, разница
    считается по ним же — при 4 %/6 % это «на 2 % дороже».
    """
    individual_income = split.get(PAYER_INDIVIDUAL, 0)
    legal_income = split.get(PAYER_LEGAL, 0)
    total = individual_income + legal_income
    if total <= 0 or legal_income <= 0:
        return None
    if legal_income * 100 <= total * NPD_LEGAL_INSIGHT_PERCENT:
        return None

    legal_label = npd_rate_label(rate_legal_bp)
    individual_label = npd_rate_label(rate_individual_bp)
    difference = npd_rate_label(rate_legal_bp - rate_individual_bp)
    return (
        f"Вы работаете с юрлицами по ставке {legal_label}. "
        f"Это на {difference} дороже, чем с физлицами ({individual_label}). "
        "Если у вас много юрлиц, убедитесь, что ваша цена для них покрывает "
        "эту разницу."
    )


def npd_context(db: Session, tutor, *, start, end) -> dict:
    """Контекст блока НПД: налог, лимит и подсказка.

    Флаг выключен — только `{"enabled": False}`: ни запросов по доходам,
    ни изменений разметки. Включён — три запроса: настройки, доход по
    типам плательщиков за период и доход с начала года.
    """
    settings = get_settings(db, tutor.id)
    if not settings.is_npd_payer:
        return {"enabled": False}

    split = earned_split(db, tutor.id, start=start, end=end)
    tax = tax_context(split, settings)
    limit = limit_context(ytd_income(db, tutor), settings.npd_income_limit)
    return {
        "enabled": True,
        "tax": tax,
        "limit": limit,
        "insight": legal_insight(
            split, settings.npd_rate_individual_bp, settings.npd_rate_legal_bp
        ),
        "note": NPD_NOTE,
        "individual_rate_label": tax["individual_rate_label"],
        "legal_rate_label": tax["legal_rate_label"],
    }