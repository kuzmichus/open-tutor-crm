"""Отображение главной страницы: интервал времени, дата платежа, месяц.

Чистые функции без БД и HTTP — по образцу `finance/services/presentation.py`.
Перевод времени в зону педагога идёт через общий `to_local` (спека
tutor-timezone), своего сдвига модуль не держит.
"""

from datetime import date, datetime

from app.common.services.tutor_time import today_local, to_local

# Короткие названия месяцев в родительном падеже: «21 окт.» у платежа.
# Вторая копия в проекте (первая — finance): цена разделения модулей,
# вынос в `app/common/` — отдельная задача, в этот change не входит.
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

# Названия месяцев для подписи «За октябрь» у карточки дохода: за месяц
# отвечает винительный падеж, он у месяцев совпадает с именительным.
_MONTHS = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)


def time_range(starts_at: datetime, ends_at: datetime, tutor) -> str:
    """«23:30 - 00:30» — границы урока в настенном времени педагога.

    Конец выводится как есть, без прижимания к 23:59: это не сетка
    календаря, а строка расписания, и урок «23:30–00:30» обязан показать
    переход через полночь (по референсу главной).
    """
    start_local = to_local(starts_at, tutor)
    end_local = to_local(ends_at, tutor)
    return f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}"


def payment_date(value: datetime | None, tutor) -> str:
    """«21 окт.» — дата платежа в зоне педагога, без года и времени."""
    if value is None:
        return ""
    local = to_local(value, tutor)
    return f"{local.day} {_MONTHS_SHORT[local.month - 1]}"


def month_caption(tutor) -> str:
    """«За октябрь» — подпись карточки дохода по текущему месяцу педагога."""
    day: date = today_local(tutor)
    return f"За {_MONTHS[day.month - 1]}"


def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        time_range=time_range,
        payment_date=payment_date,
        month_caption=month_caption,
    )
