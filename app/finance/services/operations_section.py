"""Контекст секции операций страницы финансов: вкладки, панель и балансы.

Секция `#finance-operations` — единственное, что меняется при переключении
вкладки: её отдаёт ручка `/tutor/finance/tabs/{tab}`, и htmx подменяет её
целиком (`outerHTML`) — вместе с навигацией и адресом перезапроса, чтобы
подсветка активной вкладки и `payment-saved` не отставали от содержимого.

Сборщик один на страницу (`index`), на клик по вкладке (`views/tab.py`) и на
перезапрос по событиям сохранения (`views/operations.py`): разметка и числа
не могут разойтись между полной загрузкой страницы и htmx-ответом.

`page_url` — канонический адрес открытого состояния: только сервер после
разбора query-параметров знает, что мусор в `months` стал умолчанием. Ручка
вкладки отдаёт его в `HX-Push-Url`, поэтому адресная строка и история
браузера совпадают с нарисованным.

Сервис не знает про FastAPI: на вход — сессия, репетитор и query-параметры,
на выход — контекст шаблона.
"""

from sqlalchemy.orm import Session

from app.finance.services.analytics import (
    analytics_context,
    parse_analytics_months,
)
from app.finance.services.balances import student_balances
from app.finance.services.forecast import forecast_context, parse_forecast_month
from app.finance.services.operations_feed import (
    KIND_KEYS,
    KIND_LABELS,
    TAB_KEYS,
    TAB_LABELS,
    operations_feed,
    parse_finance_tab,
)
from app.finance.services.periods import parse_finance_period
from app.finance.services.presentation import MINUS, money

# Вкладки, у которых нет ленты: своё содержимое считают графики и прогноз.
NON_FEED_TABS = ("analytics", "forecast")

PAGE_URL = "/tutor/finance"
TABS_URL = "/tutor/finance/tabs"
OPERATIONS_URL = "/tutor/finance/operations"


def parse_finance_kind(params) -> str:
    """Ключ фильтра по виду операции из query; мусор — «Все».

    Фильтр едет в адресе рядом с вкладкой (`kind=income`), чипсами и
    ссылками вкладок; опечатка не повод ломать страницу (тот же принцип,
    что у `parse_finance_tab`).
    """
    key = params.get("kind", "all")
    return key if key in KIND_KEYS else "all"


def _tab_links(period: dict, tab: str, *, months, month, kind: str) -> list[dict]:
    """Ссылки вкладок: `href` — страница целиком, `url` — ручка содержимого.

    Горизонт «Аналитики», месяц «Прогноза» и фильтр «Все операций» —
    состояние своей вкладки, поэтому в ссылку попадают только у своей
    вкладки: чужие вкладки не тащат лишний параметр в адрес, а повторный
    клик по активной вкладке не сбрасывает выбранные 12 месяцев, следующий
    месяц прогноза или чип фильтра.
    """
    links = []
    for key in TAB_KEYS:
        state = ""
        if key == "all" and kind != "all":
            state = f"&kind={kind}"
        if key == "analytics" and months is not None:
            state = f"&months={months}"
        if key == "forecast" and month is not None:
            state = f"&month={month}"
        links.append(
            {
                "key": key,
                "label": TAB_LABELS[key],
                "active": key == tab,
                "href": f"{PAGE_URL}?period={period['key']}&tab={key}{state}",
                "url": f"{TABS_URL}/{key}?period={period['key']}{state}",
            }
        )
    return links


def _kind_links(period: dict, kind: str) -> list[dict]:
    """Чипсы фильтра «Все операций»: `href` — страница, `url` — ручка вкладки.

    Чипс — тот же механизм, что у вкладок: htmx перезапрашивает секцию,
    сервер двигает адрес (`HX-Push-Url`), `href` остаётся для работы без JS.
    """
    links = []
    for key in KIND_KEYS:
        state = f"&kind={key}" if key != "all" else ""
        links.append(
            {
                "key": key,
                "label": KIND_LABELS[key],
                "active": key == kind,
                "href": f"{PAGE_URL}?period={period['key']}&tab=all{state}",
                "url": f"{TABS_URL}/all?period={period['key']}{state}",
            }
        )
    return links


def _totals_cards(income: int, refund: int, expense: int, net: int) -> list[dict]:
    """Карточки итогов ленты: подписи, готовые суммы и классы цвета.

    Приходы/возвраты/расходы — суммы строк ленты, всегда без знака; «Чистый»
    может быть отрицательным и показывается с типографским минусом. Цвет
    тоже решает сервис: шаблон не форматирует бизнес-данные сам.
    """
    return [
        {
            "label": "Приходы",
            "value": money(income),
            "value_class": "fin-ops__total-value--green",
        },
        {
            "label": "Возвраты",
            "value": money(refund),
            "value_class": "fin-ops__total-value--red",
        },
        {
            "label": "Расходы",
            "value": money(expense),
            "value_class": "fin-ops__total-value--red",
        },
        {
            "label": "Чистый",
            "value": (
                f"{MINUS}{money(abs(net))}" if net < 0 else money(net)
            ),
            "value_class": (
                "fin-ops__total-value--red" if net < 0
                else "fin-ops__total-value--green"
            ),
        },
    ]


def parse_state(params, tutor) -> dict:
    """Состояние страницы из query-параметров: период, вкладка, её настройки.

    Один разбор на все три входа (страница, клик по вкладке, перезапрос
    после сохранения): мусор в параметрах заменяется умолчаниями одинаково,
    иначе адрес и разметка разъехались бы.
    """
    return {
        "period": parse_finance_period(params, tutor),
        "tab": parse_finance_tab(params),
        "kind": parse_finance_kind(params),
        "analytics_months": parse_analytics_months(params),
        "forecast_month": parse_forecast_month(params, tutor),
    }


def operations_context(
    db: Session,
    tutor,
    *,
    period: dict,
    tab: str,
    kind: str = "all",
    analytics_months: int = 6,
    forecast_month: dict | None = None,
    oob: bool = False,
) -> dict:
    """Контекст `finance/_operations.html`: вкладка, панель, балансы, адреса.

    `analytics_months` — горизонт вкладки «Аналитика» (6/12 мес), а
    `forecast_month` — месяц вкладки «Прогноз»: на других вкладках графики
    и прогноз не строятся, и контекст их не считает.

    Фильтр `kind` действует только на вкладке «Все операции» — остальные
    лента-вкладки сами являются фильтром, и на «Аналитике»/«Прогнозе»
    ленты нет вовсе: там параметр разбирается, но не применяется и в адрес
    не попадает.

    Балансы делятся на должников и переплатчиков здесь, а не фильтрами в
    шаблоне: карточке нужны и списки, и суммы сторон — оба числа считает
    одно место (правило «шаблон не суммирует сам»).

    `oob` — ответ htmx: в него добавляются скрытые поля периода с
    `hx-swap-oob`. Форма периода живёт вне секции, и без этого она
    сохранила бы прежнюю вкладку — следующая смена периода вернула бы
    предыдущий раздел.
    """
    kind = kind if tab == "all" else "all"
    analytics = (
        analytics_context(db, tutor, months=analytics_months)
        if tab == "analytics"
        else None
    )
    forecast = (
        forecast_context(db, tutor, month=forecast_month)
        if tab == "forecast" and forecast_month is not None
        else None
    )
    # Горизонт, месяц и чип фильтра — состояние вкладки, а не страницы: они
    # входят и в адрес страницы, и в адрес перезапроса секции. Без них
    # сохранение платежа вернуло бы «Аналитику» к 6 месяцам, а «Прогноз» —
    # к текущему, и сбросило бы выбранный чип.
    months = analytics["months"] if analytics else None
    month = forecast["month"]["key"] if forecast else None
    state = f"period={period['key']}&tab={tab}"
    if tab == "all" and kind != "all":
        state += f"&kind={kind}"
    if months is not None:
        state += f"&months={months}"
    if month is not None:
        state += f"&month={month}"

    feed = (
        {"rows": []}
        if tab in NON_FEED_TABS
        else operations_feed(
            db,
            tutor.id,
            tutor,
            tab=tab,
            kind=kind,
            start=period["start"],
            end=period["end"],
        )
    )

    balances = student_balances(db, tutor.id)
    debtors = [row for row in balances if row.balance < 0]
    overpayers = [row for row in balances if row.balance > 0]
    return {
        "period": period,
        "tab": tab,
        "kind": kind,
        "oob": oob,
        "tab_labels": TAB_LABELS,
        "tabs": _tab_links(period, tab, months=months, month=month, kind=kind),
        "kind_links": _kind_links(period, kind) if tab == "all" else [],
        "page_url": f"{PAGE_URL}?{state}",
        "refresh_url": f"{OPERATIONS_URL}?{state}",
        "operations": feed["rows"],
        "totals": (
            _totals_cards(
                feed["income"], feed["refund"], feed["expense"], feed["net"]
            )
            if tab not in NON_FEED_TABS
            else []
        ),
        "analytics": analytics,
        "forecast": forecast,
        "debtors": debtors,
        "debtors_total": sum(row.balance for row in debtors),
        "overpayers": overpayers,
        "overpayers_total": sum(row.balance for row in overpayers),
    }
