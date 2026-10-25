"""Разбор форм окна: одного окна и пачки (design.md D6).

Сервис не знает про FastAPI: на вход — отображение с полями формы
(`FormData` или dict), на выход — очищенные значения и список ошибок
(паттерн `lesson_form.py` / `unavailability_form.py`).

Две формы — два набора полей:

- «Одно окно»: дата, начало, длительность из `LESSON_DURATIONS`,
  переключатель «Публичный слот»;
- «Несколько дней»: период, дни недели, рабочий интервал («Окна с» /
  «До»), длительность, перерыв, публичность.

Ошибки формулируются по-разному для каждого правила: пользователь должен
видеть, какое именно поле поправить, а не общее «проверьте форму».
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time

from app.common.services.forms import checked, text_value
from app.lesson.models.lesson import LESSON_DURATIONS

# Дни недели для чекбоксов пачки: 0 — понедельник … 6 — воскресенье
# (как `date.weekday()`).
WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

# Лимит окон за одно действие (спека slot-management, design.md D6).
MAX_SLOT_BATCH = 200

# Перерыв между окнами: 0 допустим (окна встык), отрицательный — нет.
MAX_GAP_MIN = 240


@dataclass(frozen=True)
class SlotParams:
    """Очищенные значения формы одного окна.

    `starts_at` — настенное время педагога без зоны: перевод в UTC делает
    вызывающая сторона (`slot_writer`), потому что только у неё есть
    карточка репетитора (design D3).
    """

    starts_at: datetime
    duration_min: int
    is_public: bool


@dataclass(frozen=True)
class BatchParams:
    """Очищенные значения формы пачки (design.md D6)."""

    date_from: date
    date_to: date
    weekdays: tuple[int, ...]
    day_start: time
    day_end: time
    duration_min: int
    gap_min: int
    is_public: bool
    # Ошибки уровня «форма» (лимит окон) заполняет `batch.plan()`:
    # число окон известно только после генерации.
    extra_errors: tuple[str, ...] = field(default=())


def _parse_date(raw: str) -> tuple[date | None, bool]:
    """`date` из `input[type=date]`: (значение, ошибка разбора)."""
    if raw == "":
        return None, False
    try:
        return date.fromisoformat(raw), False
    except ValueError:
        return None, True


def _parse_time(raw: str) -> tuple[time | None, bool]:
    """`time` из `input[type=time]`: (значение, ошибка разбора)."""
    if raw == "":
        return None, False
    try:
        return time.fromisoformat(raw), False
    except ValueError:
        return None, True


def _parse_int(raw: str) -> tuple[int | None, bool]:
    """Целое неотрицательное: (значение, ошибка разбора)."""
    if raw == "":
        return None, False
    if not raw.lstrip("+").isdigit():
        return None, True
    return int(raw), False


def _parse_signed_int(raw: str) -> tuple[int | None, bool]:
    """Целое со знаком: (значение, ошибка разбора).

    Нужен для перерыва: «-5» — это не мусор, а валидное число вне
    диапазона, и пользователь должен увидеть ошибку диапазона, а не
    «целое число минут».
    """
    if raw == "":
        return None, False
    digits = raw.lstrip("+-")
    if not digits.isdigit():
        return None, True
    return int(raw), False


def _parse_duration(raw: str) -> tuple[int | None, bool]:
    """Длительность из закрытого списка: (значение, ошибка)."""
    value, error = _parse_int(raw)
    if error or value is None:
        return None, error
    return (value, False) if value in LESSON_DURATIONS else (None, True)


def _weekdays_from_form(form) -> tuple[int, ...]:
    """Выбранные дни недели: повторяющееся поле `weekdays`, 0–6.

    Значения вне диапазона отбрасываются молча: это мусор из подделанного
    запроса, а не пользовательский ввод — валидатор ниже скажет «выберите
    хотя бы один день», если валидных не осталось.
    """
    raw_values = form.getlist("weekdays") if hasattr(form, "getlist") else [
        form.get("weekdays")
    ]
    days: list[int] = []
    for raw in raw_values:
        if not isinstance(raw, str):
            continue
        raw = raw.strip()
        if raw.isdigit() and 0 <= int(raw) <= 6 and int(raw) not in days:
            days.append(int(raw))
    return tuple(sorted(days))


def slot_form_values(form) -> dict:
    """Присланные значения формы одного окна — для повторного показа.

    `parse_slot_form` возвращает `None` при любой ошибке, а форма должна
    показать то, что пользователь уже ввёл, поэтому значения собираются
    напрямую из полей и не зависят от результата разбора.
    """
    values: dict = {}
    raw_date = text_value(form, "date")
    raw_time = text_value(form, "time")
    try:
        if raw_date and raw_time:
            values["starts_at"] = datetime.combine(
                date.fromisoformat(raw_date), time.fromisoformat(raw_time)
            )
    except ValueError:
        pass  # кривую дату не показываем как валидную — поля останутся пустыми
    duration, duration_error = _parse_duration(text_value(form, "duration_min"))
    if not duration_error and duration is not None:
        values["duration_min"] = duration
    values["is_public"] = checked(form, "is_public")
    return values


def parse_slot_form(form) -> tuple[SlotParams | None, list[str]]:
    """Разбор формы одного окна: значения или список ошибок.

    `starts_at` собирается из `date` + `time` как настенное время педагога.
    """
    raw_date = text_value(form, "date")
    raw_time = text_value(form, "time")
    value_date, date_error = _parse_date(raw_date)
    value_time, time_error = _parse_time(raw_time)
    duration, duration_error = _parse_duration(text_value(form, "duration_min"))

    errors: list[str] = []
    if date_error:
        errors.append("Укажите корректную дату окна.")
    elif value_date is None:
        errors.append("Укажите дату окна.")
    if time_error:
        errors.append("Укажите корректное время начала окна.")
    elif value_time is None:
        errors.append("Укажите время начала окна.")
    if duration_error:
        errors.append("Выберите длительность окна из списка.")

    if errors:
        return None, errors

    return (
        SlotParams(
            starts_at=datetime.combine(value_date, value_time),
            duration_min=duration,
            is_public=checked(form, "is_public"),
        ),
        [],
    )


def batch_form_values(form) -> dict:
    """Присланные значения формы пачки — для повторного показа.

    Как `slot_form_values`: разбор мог не удаться (пустая дата, кривой
    перерыв), а форма обязана показать введённое пользователем. Ключи
    совпадают с `BatchParams`, чтобы `dialog_context` принял словарь.
    """
    date_from, _ = _parse_date(text_value(form, "date_from"))
    date_to, _ = _parse_date(text_value(form, "date_to"))
    day_start, _ = _parse_time(text_value(form, "day_start"))
    day_end, _ = _parse_time(text_value(form, "day_end"))
    duration, duration_error = _parse_duration(text_value(form, "duration_min"))
    gap, _ = _parse_signed_int(text_value(form, "gap_min"))

    values: dict = {
        "weekdays": _weekdays_from_form(form),
        "is_public": checked(form, "is_public"),
    }
    if date_from is not None:
        values["date_from"] = date_from
    if date_to is not None:
        values["date_to"] = date_to
    if day_start is not None:
        values["day_start"] = day_start
    if day_end is not None:
        values["day_end"] = day_end
    if not duration_error and duration is not None:
        values["duration_min"] = duration
    if gap is not None:
        values["gap_min"] = gap
    return values


def parse_batch_form(form) -> tuple[BatchParams | None, list[str]]:
    """Разбор формы пачки: значения или список ошибок (design.md D6).

    Проверки: конец периода не раньше начала, хотя бы один день недели,
    «До» позже «С», длительность из списка, перерыв не отрицательный.
    Каждое правило даёт своё сообщение.
    """
    date_from, from_error = _parse_date(text_value(form, "date_from"))
    date_to, to_error = _parse_date(text_value(form, "date_to"))
    day_start, start_error = _parse_time(text_value(form, "day_start"))
    day_end, end_error = _parse_time(text_value(form, "day_end"))
    duration, duration_error = _parse_duration(text_value(form, "duration_min"))
    gap, gap_error = _parse_signed_int(text_value(form, "gap_min"))
    weekdays = _weekdays_from_form(form)

    errors: list[str] = []
    if from_error:
        errors.append("Укажите корректное начало периода.")
    elif date_from is None:
        errors.append("Укажите начало периода.")
    if to_error:
        errors.append("Укажите корректный конец периода.")
    elif date_to is None:
        errors.append("Укажите конец периода.")
    if not weekdays:
        errors.append("Выберите хотя бы один день недели.")
    if start_error:
        errors.append("Укажите корректное время «Окна с».")
    elif day_start is None:
        errors.append("Укажите время «Окна с».")
    if end_error:
        errors.append("Укажите корректное время «До».")
    elif day_end is None:
        errors.append("Укажите время «До».")
    if duration_error:
        errors.append("Выберите длительность окна из списка.")
    if gap_error:
        errors.append("Перерыв — целое число минут.")
    elif gap is not None and not 0 <= gap <= MAX_GAP_MIN:
        errors.append(f"Перерыв — от 0 до {MAX_GAP_MIN} минут.")

    # Правила сравнения проверяются только когда оба значения разобрались:
    # иначе к «конец раньше начала» добавилась бы ошибка разбора того же поля.
    if date_from is not None and date_to is not None and date_to < date_from:
        errors.append("Конец периода не раньше начала.")
    if day_start is not None and day_end is not None and day_end <= day_start:
        errors.append("Время «До» должно быть позже «Окна с».")

    if errors:
        return None, errors

    return (
        BatchParams(
            date_from=date_from,
            date_to=date_to,
            weekdays=weekdays,
            day_start=day_start,
            day_end=day_end,
            duration_min=duration,
            # Пустой перерыв — 0: окна встык, это допустимо.
            gap_min=gap or 0,
            is_public=checked(form, "is_public"),
        ),
        [],
    )
