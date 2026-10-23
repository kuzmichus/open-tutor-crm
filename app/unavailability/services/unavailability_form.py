"""Разбор формы отметки недоступности и контекст панели (design.md D8).

Сервис не знает про FastAPI: на вход — отображение с полями формы
(`FormData` или dict), на выход — очищенные значения и список ошибок
(паттерн `lesson_form.py` / `homework_form.py`).

Два режима — два набора полей (design.md D1):

- «Период»: причина из закрытого списка, первый день обязателен,
  последний не раньше первого; пустой последний день — бессрочно;
- «Постоянный выходной»: день недели 0–6 обязателен, причина всегда
  «Выходной», «Действует по» необязательно.

Панель показывает список «Уже отмечено» (design.md D11): активные отметки
по возрастанию первого дня, прошедшие — отдельно под «Показать прошедшие».
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.common.services.tutor_time import today_local
from app.tutor.models.tutor import Tutor
from app.unavailability.models.unavailability import (
    DAYOFF_REASON,
    PERIOD_REASONS,
    REASON_LABELS,
    UNAVAILABILITY_MODES,
    WEEKDAY_LABELS,
)
from app.unavailability.services.marks import list_marks

# Режимы с подписями для переключателя панели.
MODE_LABELS = {
    "period": "Период",
    "weekday": "Постоянный выходной",
}


@dataclass(frozen=True)
class MarkRow:
    """Строка списка «Уже отмечено»: сама отметка и признак прошедшей."""

    mark: object
    is_past: bool


def _text(form, name: str) -> str:
    """Значение поля формы как строка (нет значения — пустая строка)."""
    value = form.get(name)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _parse_date(raw: str) -> tuple[date | None, bool]:
    """`date` из `input[type=date]`: (значение, ошибка разбора).

    Пустая строка — «не указано» без ошибки; кривая — ошибка.
    """
    if raw == "":
        return None, False
    try:
        return date.fromisoformat(raw), False
    except ValueError:
        return None, True


def _parse_weekday(raw: str) -> tuple[int | None, bool]:
    """День недели 0–6: (значение, ошибка разбора)."""
    if raw == "":
        return None, False
    if not raw.isdigit():
        return None, True
    value = int(raw)
    if not 0 <= value <= 6:
        return None, True
    return value, False


def parse_unavailability_form(form) -> tuple[dict, list[str]]:
    """Данные формы отметки и ошибки разбора.

    Возвращает `(данные, ошибки)`; данные содержат только очищенные
    значения полей панели — режим решает, какие из них значимы.
    """
    mode = _text(form, "mode") or "period"
    reason = _text(form, "reason")
    start_date, start_error = _parse_date(_text(form, "start_date"))
    end_date, end_error = _parse_date(_text(form, "end_date"))
    weekday, weekday_error = _parse_weekday(_text(form, "weekday"))
    until_date, until_error = _parse_date(_text(form, "until_date"))

    data = {
        "mode": mode,
        "reason": reason or None,
        "start_date": start_date,
        "end_date": end_date,
        "weekday": weekday,
        "until_date": until_date,
    }

    errors: list[str] = []
    if start_error:
        errors.append("Укажите корректный первый день.")
    if end_error:
        errors.append("Укажите корректный последний день.")
    if weekday_error:
        errors.append("Выберите день недели.")
    if until_error:
        errors.append("Укажите корректную дату «Действует по».")

    errors.extend(validate_unavailability_data(data))
    return data, errors


def validate_unavailability_data(data: dict) -> list[str]:
    """Проверки очищенных значений — те же правила, что в CHECK БД.

    Дублируются в writer'е: форма могла прийти в обход разбора, а БД
    ограничения проверяет только на уровне SQL.
    """
    errors: list[str] = []

    mode = data.get("mode")
    if mode not in UNAVAILABILITY_MODES:
        return ["Выберите режим отметки."]

    if mode == "period":
        if data.get("reason") not in PERIOD_REASONS:
            errors.append("Выберите причину недоступности.")
        if data.get("start_date") is None:
            errors.append("Укажите первый день.")
        elif data.get("end_date") is not None and data["end_date"] < data["start_date"]:
            errors.append("Последний день не раньше первого.")
    else:
        weekday = data.get("weekday")
        if weekday is None or not 0 <= weekday <= 6:
            errors.append("Выберите день недели.")

    return errors


def parse_end_form(form) -> tuple[date | None, list[str]]:
    """Новый срок из формы «Изменить срок»: (дата или None, ошибки).

    Поле называется `end_date` у периода и `until_date` у выходного, но
    принимается одно имя `new_end` — эндпоинт не знает режим до выборки
    отметки, а режим определяет, какое поле записи менять (design.md D9).
    Пустое значение — бессрочно, без ошибки.
    """
    new_end, error = _parse_date(_text(form, "new_end"))
    if error:
        return None, ["Укажите корректный последний день."]
    return new_end, []


def validate_end_change(mark, new_end: date | None) -> list[str]:
    """Новый срок отметки: для периода — не раньше первого дня.

    Сокращать прошедшую отметку можно, поэтому «не раньше сегодня»
    не требуется (design.md D9).
    """
    if (
        mark.mode == "period"
        and new_end is not None
        and mark.start_date is not None
        and new_end < mark.start_date
    ):
        return ["Последний день не раньше первого."]
    return []


def _is_past(mark, today: date) -> bool:
    """Срок отметки истёк: прошедшие прячутся под «Показать прошедшие»."""
    if mark.mode == "period":
        return mark.end_date is not None and mark.end_date < today
    return mark.until_date is not None and mark.until_date < today


def _sort_key(row: MarkRow):
    """Активные раньше прошедших, внутри — по первому дню.

    У постоянного выходного первого дня нет — он действует всегда, поэтому
    идёт раньше датированных отметок (`date.min`); при равенстве порядок
    задаёт дата создания, чтобы список не «прыгал» между рендерами.
    """
    mark = row.mark
    first_day = mark.start_date or date.min
    return (row.is_past, first_day, mark.created_at or date.min)


def mark_rows(marks: list, today: date | None = None) -> list[MarkRow]:
    """Строки списка с признаком прошедшей отметки, в порядке D11.

    `today` — дата в зоне педагога (design.md D7): прошедшей считается
    отметка, чей срок истёк именно для его календаря.
    """
    today = today or date.today()
    rows = [MarkRow(mark=mark, is_past=_is_past(mark, today)) for mark in marks]
    return sorted(rows, key=_sort_key)


def panel_context(
    db: Session,
    tutor_id: str,
    *,
    data: dict | None = None,
    errors: list[str] | None = None,
    saved: bool = False,
    today: date | None = None,
) -> dict:
    """Контекст панели «Отпуск и выходные» (design.md D8).

    Ключи с префиксом `un_`: панель рендерится в `#modal` отдельно, но
    префикс не даёт ей столкнуться с контекстом формы урока, если её
    когда-нибудь вставят через `include`.

    `data` — присланные значения формы при ошибке: панель показывает
    введённое пользователем, а не сброшенные поля (паттерн
    `lesson_form_context`).

    `today` по умолчанию — сегодняшняя дата в зоне педагога
    (`today_local`, design.md D7): отметка считается прошедшей по его
    календарю, а не по календарю сервера. Явный аргумент оставлен для
    сервисных тестов.
    """
    today = today or today_local(db.get(Tutor, tutor_id))
    rows = mark_rows(list_marks(db, tutor_id), today=today)
    active = [row for row in rows if not row.is_past]
    past = [row for row in rows if row.is_past]

    values = {
        "mode": "period",
        "reason": PERIOD_REASONS[0],
        "start_date": "",
        "end_date": "",
        "weekday": "",
        "until_date": "",
    }
    if data is not None:
        values.update(
            {
                "mode": data.get("mode") or "period",
                "reason": data.get("reason") or PERIOD_REASONS[0],
                "start_date": _input_date(data.get("start_date")),
                "end_date": _input_date(data.get("end_date")),
                "weekday": (
                    "" if data.get("weekday") is None else str(data["weekday"])
                ),
                "until_date": _input_date(data.get("until_date")),
            }
        )

    return {
        "un_form": values,
        "un_errors": errors or [],
        "un_saved": saved,
        "un_active": active,
        "un_past": past,
        "un_modes": UNAVAILABILITY_MODES,
        "un_mode_labels": MODE_LABELS,
        "un_reasons": PERIOD_REASONS,
        "un_reason_labels": REASON_LABELS,
        "un_dayoff_reason": DAYOFF_REASON,
        "un_weekdays": WEEKDAY_LABELS,
    }


def _input_date(value) -> str:
    """Значение для `input[type=date]`: «YYYY-MM-DD»."""
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")
