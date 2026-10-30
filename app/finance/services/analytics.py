"""Вкладка «Аналитика» страницы финансов: месячные ряды и категории расходов.

Горизонт аналитики задают пилюли «6 мес» / «12 мес» (query-параметр `months`)
— он не зависит от селектора периода сводки: сводка отвечает на вопрос
«что происходит в выбранном окне», аналитика — «как менялось полгода-год».

Два графика по референсу:

- «Доходы и расходы по месяцам» — группированные столбцы трёх рядов:
  «Доход» (оплаченные платежи), «Заработано» (списания за проведённые
  уроки), «Расходы» (траты репетитора). Семантика рядов — та же, что у
  карточек сводки (`summary.period_flow`): числа вкладки и сводки не могут
  рассказывать о деньгах по-разному.
- «Расходы по категориям» — пирог с долями категорий трат и легендой.

Геометрия обоих графиков считается здесь, а не в шаблоне: шаблон печатает
готовые координаты (правило «шаблон не форматирует бизнес-данные сам»),
и разметку можно проверять тестами без браузера. Месяцы группируются по
настенному времени педагога: `strftime` в SQL резал бы месяцы по UTC и
при ненулевой зоне у талонных операций уезжал бы в соседний столбец.

Сервис не знает про FastAPI: на вход — сессия, репетитор и горизонт,
на выход — контекст для `finance/_analytics.html`.
"""

import math
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.services.tutor_time import local_day_bounds, to_local, today_local
from app.finance.models.account_operation import BALANCE_PAYMENT_STATUS, AccountOperation
from app.finance.models.expense import EXPENSE_CATEGORIES, EXPENSE_CATEGORY_LABELS, Expense
from app.finance.services.presentation import money
from app.student.models.student import Student

# Горизонты графика в месяцах (включая текущий); 6 — умолчание.
MONTHS_OPTIONS = (6, 12)
MONTHS_LABELS = {6: "6 мес", 12: "12 мес"}

# Ряды столбчатого графика: порядок легенды и баров одной константой.
SERIES_LABELS = {
    "income": "Доход",
    "earned": "Заработано",
    "expenses": "Расходы",
}

# Подписи оси X — короткие месяцы в именительном падеже («Май», не «мая»):
# ось называет месяц, а не дату внутри него.
_MONTHS_NOMINATIVE = (
    "Янв",
    "Фев",
    "Мар",
    "Апр",
    "Май",
    "Июн",
    "Июл",
    "Авг",
    "Сен",
    "Окт",
    "Ноя",
    "Дек",
)

# Цветовые моды категорий пирога: категория → индекс класса `fin-slice--N`.
# Индекс фиксирован за категорией (порядок `EXPENSE_CATEGORIES` модели),
# а не за местом в топе: цвет «Рекламы» не должен меняться от того,
# потратился ли в этом месяце транспорт.
CATEGORY_COLOR_INDEX = {
    category: index + 1 for index, category in enumerate(EXPENSE_CATEGORIES)
}
FALLBACK_COLOR_INDEX = len(EXPENSE_CATEGORIES)

# Холст столбчатого графика. Ширина 720 рассчитана на колонку контента,
# viewBox + width:100% в CSS растягивают его без пересчёта координат.
_CHART_WIDTH = 720
_CHART_HEIGHT = 260
_CHART_PAD_LEFT = 48  # место под подписи делений оси Y
_CHART_PAD_RIGHT = 8
_CHART_PAD_TOP = 8
_CHART_PAD_BOTTOM = 26  # подписи месяцев под базовой линией
_BAR_GAP = 4  # промежуток между столбцами одной группы
_BAR_RX = 3  # скругление столбца: у референса бары слегка скруглены

# Пирог: квадратный холст, подписи долей — снаружи кольца.
_PIE_SIZE = 260
_PIE_RADIUS = 84
_PIE_LABEL_RADIUS = 108
# Доли меньше 5% снаружи не подписываются: подписи соседей слипаются,
# точное число всё равно называет легенда под графиком.
_PIE_MIN_LABEL_PERCENT = 5


def parse_analytics_months(params) -> int:
    """Горизонт из query; мусор и опечатки — умолчание 6.

    Параметр ставят пилюли-ссылки, поэтому значения закрыты `MONTHS_OPTIONS`
    (тот же принцип, что у `parse_finance_period`: опечатка не повод
    ломать страницу).
    """
    try:
        value = int(params.get("months", MONTHS_OPTIONS[0]))
    except (TypeError, ValueError):
        return MONTHS_OPTIONS[0]
    return value if value in MONTHS_OPTIONS else MONTHS_OPTIONS[0]


def _month_keys(tutor, *, months: int) -> list[tuple[int, int]]:
    """Ключи (год, месяц) от старейшего к текущему — по зоне педагога.

    Арифметика в «абсолютных месяцах» (год×12+месяц), а не сдвиг дней:
    вычитание 32×N дней из первого числа уезжает через месяц при длинных
    месяцах (1 октября − 64 дня = 28 августа, а не 1 августа).
    """
    today = today_local(tutor)
    anchor = today.year * 12 + today.month - 1
    return [
        ((anchor - back) // 12, (anchor - back) % 12 + 1)
        for back in range(months - 1, -1, -1)
    ]


def _month_window(month_keys: list[tuple[int, int]], tutor) -> tuple:
    """Окно `[start, end)` всех месяцев списка как aware-UTC-границы."""
    oldest = date(month_keys[0][0], month_keys[0][1], 1)
    newest = date(month_keys[-1][0], month_keys[-1][1], 1)
    after_newest = (newest + timedelta(days=32)).replace(day=1)
    start = local_day_bounds(oldest, tutor)[0]
    end = local_day_bounds(after_newest, tutor)[0]
    return start, end


def _flow_by_month(db: Session, tutor_id: str, tutor, *, start, end) -> tuple:
    """«Доход» и «Заработано» по месяцам зоны педагога.

    Правила сумм — те же, что у сводки (`period_flow`): в доход идут только
    оплаченные платежи, заработано — списания за уроки; возвраты и ожидающие
    платежи график денег репетитора не рисуют.
    """
    rows = db.execute(
        select(
            AccountOperation.occurred_at,
            AccountOperation.kind,
            AccountOperation.status,
            AccountOperation.amount,
        )
        .join(Student, Student.id == AccountOperation.student_id)
        .where(
            Student.tutor_id == tutor_id,
            AccountOperation.occurred_at >= start,
            AccountOperation.occurred_at < end,
        )
    ).all()

    income: dict[tuple[int, int], int] = {}
    earned: dict[tuple[int, int], int] = {}
    for occurred_at, kind, status_value, amount in rows:
        local = to_local(occurred_at, tutor)
        key = (local.year, local.month)
        if kind == "payment" and status_value == BALANCE_PAYMENT_STATUS:
            income[key] = income.get(key, 0) + amount
        elif kind == "lesson":
            earned[key] = earned.get(key, 0) + amount
    return income, earned


def _expenses_by_month_and_category(db: Session, tutor_id: str, tutor, *, start, end) -> tuple:
    """Траты одним проходом: по месяцам для столбцов и по категориям для пирога."""
    rows = db.scalars(
        select(Expense).where(
            Expense.tutor_id == tutor_id,
            Expense.spent_at >= start,
            Expense.spent_at < end,
        )
    ).all()

    by_month: dict[tuple[int, int], int] = {}
    by_category: dict[str, int] = {}
    for expense in rows:
        local = to_local(expense.spent_at, tutor)
        key = (local.year, local.month)
        by_month[key] = by_month.get(key, 0) + expense.amount
        by_category[expense.category] = by_category.get(expense.category, 0) + expense.amount
    return by_month, by_category


def _thousands(value: int) -> str:
    """«10 000» — подпись деления оси без ₽, с неразрывным пробелом.

    Валюта не повторяется на каждом делении: ось подписана числами, валюта
    понятна из контекста страницы финансов (как на референсе).
    """
    return f"{value:,}".replace(",", "\u00a0")


def _y_ticks(max_value: int) -> list[int]:
    """Деления оси Y из ряда 1/2/5×10ⁿ — не больше пяти подписей.

    «Красивые» шаги держат подписи круглыми: деления «7 000 / 14 000»
    читаются хуже, чем «10 000 / 20 000».
    """
    magnitude = 10 ** (len(str(max_value)) - 1)
    step = magnitude
    intervals = max_value
    for factor in (1, 2, 5, 10):
        candidate = magnitude * factor
        intervals = -(-max_value // candidate)  # ceil без math
        step = candidate
        if intervals <= 4:
            break
    return [i * step for i in range(intervals + 1)]


def _bar_chart(
    month_keys: list[tuple[int, int]],
    income: dict,
    earned: dict,
    expenses_by_month: dict,
) -> dict | None:
    """Геометрия SVG столбчатого графика; None — за период не было ни рубля.

    Все координаты — числа с одним знаком: дробные пиксели SVG не нужны,
    а целые держат разметку стабильной для тестов.
    """
    top_value = 0
    for key in month_keys:
        top_value = max(
            top_value,
            income.get(key, 0),
            earned.get(key, 0),
            expenses_by_month.get(key, 0),
        )
    if top_value <= 0:
        return None

    ticks = _y_ticks(top_value)
    axis_max = ticks[-1]

    plot_left = _CHART_PAD_LEFT
    plot_right = _CHART_WIDTH - _CHART_PAD_RIGHT
    baseline = _CHART_HEIGHT - _CHART_PAD_BOTTOM
    plot_height = baseline - _CHART_PAD_TOP
    plot_width = plot_right - plot_left

    gridlines = [
        {
            "y": round(baseline - (tick / axis_max) * plot_height, 1),
            "label": _thousands(tick),
        }
        for tick in ticks
    ]

    values_by_series = {
        "income": income,
        "earned": earned,
        "expenses": expenses_by_month,
    }
    group_width = plot_width / len(month_keys)
    # Ширина столбца: узкая на 12 месяцах (иначе группы слипаются),
    # но не меньше 8 и не больше 20 пикселей — пропорции референса.
    bar_width = max(8.0, min(20.0, group_width / 4.5))

    groups = []
    for index, key in enumerate(month_keys):
        cluster_width = 3 * bar_width + 2 * _BAR_GAP
        cluster_x = plot_left + index * group_width + (group_width - cluster_width) / 2
        bars = []
        for series_i, series in enumerate(SERIES_LABELS):
            value = values_by_series[series].get(key, 0)
            if value <= 0:
                # Нулевой столбец не рисуется вовсе: высота 0 и рамка
                # в полпикселя — визуальный мусор у пустых месяцев.
                continue
            height = (value / axis_max) * plot_height
            bars.append(
                {
                    "series": series,
                    "x": round(cluster_x + series_i * (bar_width + _BAR_GAP), 1),
                    "y": round(baseline - height, 1),
                    "width": round(bar_width, 1),
                    "height": round(height, 1),
                }
            )
        groups.append(
            {
                "label": _MONTHS_NOMINATIVE[key[1] - 1],
                "x": round(plot_left + (index + 0.5) * group_width, 1),
                "bars": bars,
            }
        )

    return {
        "width": _CHART_WIDTH,
        "height": _CHART_HEIGHT,
        "pad_left": _CHART_PAD_LEFT,
        "plot_right": plot_right,
        "baseline": baseline,
        "gridlines": gridlines,
        "groups": groups,
    }


def _slice_path(cx: float, cy: float, radius: int, start: float, end: float) -> str:
    """SVG-path сектора пирога от угла `start` до `end` (радианы, по часовой).

    Сектор в 360° (единственная категория) — два полукруга: дуга с теми же
    началом и концом ничего не рисует, и пирог «исчез» бы у репетитора
    с одним видом трат.
    """
    if end - start >= 2 * math.pi - 1e-9:
        top, bottom = cy - radius, cy + radius
        return (
            f"M {cx:.1f} {top:.1f} "
            f"A {radius} {radius} 0 1 1 {cx:.1f} {bottom:.1f} "
            f"A {radius} {radius} 0 1 1 {cx:.1f} {top:.1f} Z"
        )
    x0 = cx + radius * math.cos(start)
    y0 = cy + radius * math.sin(start)
    x1 = cx + radius * math.cos(end)
    y1 = cy + radius * math.sin(end)
    large_arc = 1 if end - start > math.pi else 0
    return (
        f"M {cx:.1f} {cy:.1f} L {x0:.1f} {y0:.1f} "
        f"A {radius} {radius} 0 {large_arc} 1 {x1:.1f} {y1:.1f} Z"
    )


def _label_anchor(cosine: float) -> str:
    """Привязка текста доли по стороне пирога: слева/справа/по центру сверху."""
    if cosine < -0.2:
        return "end"
    if cosine > 0.2:
        return "start"
    return "middle"


def _pie_chart(by_category: dict[str, int]) -> dict | None:
    """Геометрия SVG пирога категорий и строки легенды; None — трат нет.

    Доли округляются до целых процентов: десятые на пиксельной диаграмме
    не читаются, точную сумму называет легенда.
    """
    total = sum(by_category.values())
    if total <= 0:
        return None

    cx = cy = _PIE_SIZE / 2
    # Отсчёт с 12 часов по часовой — привычное направление круговых
    # диаграмм; сектора идут от большего к меньшему, как на референсе.
    ordered = sorted(by_category.items(), key=lambda item: (-item[1], item[0]))

    slices = []
    legend = []
    angle = -math.pi / 2
    for category, amount in ordered:
        share = amount / total
        end_angle = angle + share * 2 * math.pi
        mid = (angle + end_angle) / 2
        percent = round(share * 100)
        cosine = math.cos(mid)
        color_index = CATEGORY_COLOR_INDEX.get(category, FALLBACK_COLOR_INDEX)
        slices.append(
            {
                "d": _slice_path(cx, cy, _PIE_RADIUS, angle, end_angle),
                "color_index": color_index,
                "percent": percent,
                "show_label": percent >= _PIE_MIN_LABEL_PERCENT,
                "label_x": round(cx + _PIE_LABEL_RADIUS * cosine, 1),
                "label_y": round(cy + _PIE_LABEL_RADIUS * math.sin(mid), 1),
                "anchor": _label_anchor(cosine),
            }
        )
        legend.append(
            {
                "label": EXPENSE_CATEGORY_LABELS.get(category, category),
                "percent": percent,
                "amount": money(amount),
                "color_index": color_index,
            }
        )
        angle = end_angle

    return {"size": _PIE_SIZE, "slices": slices, "legend": legend}


def analytics_context(db: Session, tutor, *, months: int) -> dict:
    """Контекст `finance/_analytics.html`: горизонт, графики, легенды."""
    month_keys = _month_keys(tutor, months=months)
    start, end = _month_window(month_keys, tutor)
    income, earned = _flow_by_month(db, tutor.id, tutor, start=start, end=end)
    expenses_by_month, by_category = _expenses_by_month_and_category(
        db, tutor.id, tutor, start=start, end=end
    )
    return {
        "months": months,
        "months_options": MONTHS_OPTIONS,
        "months_labels": MONTHS_LABELS,
        "series_labels": SERIES_LABELS,
        "bar_chart": _bar_chart(month_keys, income, earned, expenses_by_month),
        "pie_chart": _pie_chart(by_category),
    }
