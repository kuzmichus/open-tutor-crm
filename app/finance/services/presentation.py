"""Отображение счёта: деньги, знак суммы, подписи вида и статуса, дата.

Чистые функции без БД и HTTP (как `group/services/presentation.py`):
принимают значения модели и возвращают строки для шаблона. Бизнес-правила
живут в других сервисах модуля — здесь только формат.

Формат денег — «1 200 ₽» с неразрывным пробелом между разрядами и перед
знаком рубля: число не должно переноситься отдельно от валюты. Третья
копия форматтера в проекте (`group`, `lesson`, теперь `finance`) — цена
разделения модулей; вынос общего в `app/common/` — отдельная задача
(design D14), в этот change не входит.

Знак суммы выводится из вида операции (`balance.signed_amount`), а не
хранится в числе: минус — типографский U+2212, как на референсе, а не
дефис. Подписи видов и статусов берутся из закрытых списков модели —
одного источника истины с CHECK-ограничениями.
"""

from datetime import datetime
from decimal import Decimal

from app.common.services.tutor_time import to_local
from app.finance.models.account_operation import (
    OPERATION_KIND_LABELS,
    PAYMENT_FALLBACK_LABEL,
    PAYMENT_METHOD_LABELS,
    PAYMENT_STATUS_LABELS,
    AccountOperation,
)
from app.finance.models.expense import EXPENSE_CATEGORY_LABELS
from app.finance.services.balance import signed_amount

# Типографский минус (U+2212), а не дефис-минус: в числах он читается
# как знак, а не как перенос строки (design D14).
MINUS = "\u2212"

# Короткие названия месяцев в родительном падеже: «22 окт. 2026, 01:31».
_MONTHS_SHORT = (
    "янв.",
    "февр.",
    "мар.",
    "апр.",
    "мая",
    "июн.",
    "июл.",
    "авг.",
    "сент.",
    "окт.",
    "нояб.",
    "дек.",
)


def money(value: int | None) -> str:
    """«1 200 ₽»; нет значения — пустая строка (блока суммы нет).

    Разделитель разрядов — неразрывный пробел, как в `group` и `lesson`:
    «1 200» не должно разъезжаться по двум строкам.
    """
    if value is None:
        return ""
    return f"{value:,}".replace(",", "\u00a0") + "\u00a0₽"


def signed_money(operation: AccountOperation) -> str:
    """Сумма со знаком: «+2 000 ₽» у платежа, «−1 200 ₽» у возврата и урока.

    Знак берётся из той же формулы, что и баланс (`signed_amount`): если
    бы шаблон выводил знак сам, сумма строк истории могла бы разойтись с
    числом в карточке баланса.
    """
    value = signed_amount(operation.kind, operation.status, operation.amount)
    sign = MINUS if value < 0 else "+"
    return f"{sign}{money(abs(value))}"


def balance_label(value: int) -> str:
    """Баланс со знаком: «−200 ₽» при долге, «0 ₽» и «800 ₽» без плюса.

    Плюс у положительного баланса не ставится: это не движение денег, а
    состояние счёта. Отрицательный показывается как есть — ограничения
    «не ниже нуля» у баланса нет (design D5).
    """
    if value < 0:
        return f"{MINUS}{money(abs(value))}"
    return money(value)


def operation_kind_label(operation: AccountOperation) -> str:
    """Вид операции в истории: «Перевод», «Возврат средств», «Урок».

    У платежа подписью служит способ («Перевод»/«Карта»/«Онлайн»): строка
    говорит, как пришли деньги, а не только «платёж». Способ не задан —
    нейтральное «Платёж».
    """
    if operation.kind == "payment":
        return PAYMENT_METHOD_LABELS.get(operation.method or "", PAYMENT_FALLBACK_LABEL)
    return OPERATION_KIND_LABELS.get(operation.kind, operation.kind)


def payment_status_label(status: str | None) -> str:
    """Подпись статуса платежа: «Оплачено» / «Ожидает» / «Отменено»."""
    return PAYMENT_STATUS_LABELS.get(status or "", status or "")


def payment_method_label(method: str | None) -> str:
    """Подпись способа платежа: «Перевод» / «Карта» / «Онлайн»."""
    return PAYMENT_METHOD_LABELS.get(method or "", method or "")


def expense_category_label(category: str | None) -> str:
    """Подпись категории расхода: «Аренда», «Реклама», …; вне списка — как есть."""
    return EXPENSE_CATEGORY_LABELS.get(category or "", category or "")


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Русская форма слова по числу: «1 ученик», «2 ученика», «5 учеников».

    Единственное место с правилом плюрализации модуля: и «занятие», и
    «ученик» склоняются одинаково, а вторая копия правила разошлась бы с
    первой на 11–14 (у них окончание «многих», хотя последняя цифра 1–4).
    """
    if count % 100 in (11, 12, 13, 14):
        return many
    if count % 10 == 1:
        return one
    if count % 10 in (2, 3, 4):
        return few
    return many


def lessons_count_label(count: int) -> str:
    """«1 занятие» / «2 занятия» / «5 занятий» — русская плюрализация.

    Ноль подписывается как «0 занятий», но вызывающие его не показывают:
    при пустом периоде такая подпись читалась бы как данные, а не как их
    отсутствие (правило student-management о показе нулей).
    """
    return f"{count} {_plural(count, 'занятие', 'занятия', 'занятий')}"


def operation_datetime(value: datetime | None, tutor) -> str:
    """«22 окт. 2026, 01:31» — дата и время операции в зоне педагога.

    Значение хранится в UTC, а показывается настенным временем педагога
    (спека student-finance, «Время платежа в зоне педагога»): перевод —
    через общий `to_local`, своего сдвига у модуля нет.
    """
    if value is None:
        return ""
    local = to_local(value, tutor)
    return (
        f"{local.day} {_MONTHS_SHORT[local.month - 1]} {local.year}, "
        f"{local.strftime('%H:%M')}"
    )


def duration_label(minutes: int) -> str:
    """Длительность астрономическим временем: «1 ч 30 мин», «45 мин», «0 мин».

    Часы и минуты показываются вместе только когда есть обе части: «1 ч 0
    мин» читалось бы как точность, которой нет. Часы не дробятся — 90 минут
    это «1 ч 30 мин», а не «1,5 ч»: подпись «Проведено» отвечает на вопрос
    «сколько это в часах и минутах», а не «сколько это часов в долях».
    """
    if minutes <= 0:
        return "0 мин"
    hours, rest = divmod(int(minutes), 60)
    if hours and rest:
        return f"{hours} ч {rest} мин"
    if hours:
        return f"{hours} ч"
    return f"{rest} мин"

def _decimal(value: float) -> str:
    """Число с одним знаком после запятой; целые — без дробной части."""
    if abs(value - round(value)) < 0.05:
        return str(round(value))
    return f"{value:.1f}".replace(".", ",")

def rate_label(value: int | None) -> str:
    """Средняя стоимость часа: «800 ₽/ч»; значения нет — «—».

    Прочерк, а не «0 ₽/ч»: часов без выручки не бывает в данных, и ноль
    здесь означал бы измеренную величину, а не отсутствие базы расчёта.
    """
    if value is None:
        return "—"
    return f"{money(value)}/ч"

def npd_rate_label(rate: Decimal) -> str:
    """Ставка НПД в процентах: «4 %», «6 %», «4,5 %».

    Ставка приходит из настроек профиля (`npd_tax_rate_individual` и
    `npd_tax_rate_legal_entity`) как Decimal: хвостовые нули не печатаются,
    дробная часть — через запятую, как принято в русской типографике.
    """
    value = Decimal(rate).normalize()
    if value == value.to_integral_value():
        return f"{int(value)}\u00a0%"
    return f"{value}".replace(".", ",") + "\u00a0%"

def _hours_word(hours: float) -> str:
    """Склонение «час/часа/часов» для дробного или целого значения."""
    if abs(hours - round(hours)) >= 0.05:
        return "часа"
    value = abs(round(hours))
    last_two = value % 100
    last = value % 10
    if 11 <= last_two <= 14:
        return "часов"
    if last == 1:
        return "час"
    if 2 <= last <= 4:
        return "часа"
    return "часов"

def free_hours_phrase(minutes: int) -> str:
    """«10,5 свободных часов», «1 свободный час», «2 свободных часа».

    Прилагательное согласуется с числом так же, как существительное:
    «1 свободный час», «2 свободных часа», «5 свободных часов»; у дробного
    значения — форма родительного единственного («1,5 свободных часа»),
    как в живой речи.
    """
    hours = minutes / 60
    number = _decimal(hours)
    if abs(hours - round(hours)) >= 0.05:
        return f"{number} свободных часа"
    word = _hours_word(hours)
    if word == "час":
        return f"{number} свободный час"
    return f"{number} свободных {word}"

def balance_notice_label(count: int, missing: int) -> str:
    """«Сегодня занятие у 1 ученика, а на счёте не хватает 1 500 ₽».

    Подпись плашки о нехватке денег на сегодняшние уроки. После «у» нужен
    родительный падеж: «у 1 ученика», «у 2 учеников», «у 21 ученика» —
    форму единственного числа даёт последняя цифра, кроме 11–14 (правило
    общее с `lessons_count_label`). «Занятие» стоит в единственном числе
    только при одном ученике: у двух и более занятий несколько, поэтому
    «Сегодня занятия у 2 учеников», в том числе «у 21 ученика». Деньги —
    через `money()`, чтобы сумма читалась так же, как в счёте ученика.
    """
    students_word = _plural(count, "ученика", "учеников", "учеников")
    lesson_word = "занятие" if count == 1 else "занятия"
    return (
        f"Сегодня {lesson_word} у {count} {students_word}, "
        f"а на счёте не хватает {money(missing)}"
    )


def ratio_label(ratio: float) -> str:
    """Во сколько раз: «2 раза», «1,5 раза», «3 раза».

    «Раз» после «в» всегда в форме «раза» — «в 2 раза», «в 5 раза» не
    бывает, поэтому отдельного склонения не нужно.
    """
    return f"{_decimal(ratio)} раза"

def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        money=money,
        signed_money=signed_money,
        balance_label=balance_label,
        operation_kind_label=operation_kind_label,
        payment_status_label=payment_status_label,
        payment_method_label=payment_method_label,
        expense_category_label=expense_category_label,
        operation_datetime=operation_datetime,
        lessons_count_label=lessons_count_label,
        duration_label=duration_label,
        rate_label=rate_label,
        npd_rate_label=npd_rate_label,
        free_hours_phrase=free_hours_phrase,
        ratio_label=ratio_label,
        balance_notice_label=balance_notice_label,
    )
