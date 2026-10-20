"""Генерация дат повторяющегося расписания (решение D2).

Слоты серии — объекты вида `{"weekday": 0..6, "start_time": "HH:MM",
"end_time": "HH:MM"}` (решение D1; `weekday` 0 = понедельник …
6 = воскресенье, как в `date.weekday()`). Функции чистые: не трогают БД
и HTTP, годятся для тестов без фикстур.

Считаются только даты начала уроков: от `starts_at.date()` для каждого
слота — первый день недели слота, не раньше даты начала, далее через
`interval_weeks` недель, пока дата не превысит `until_date` (включительно).
`end_time` слота участвует только в панели расписания; длительность
создаваемых уроков берётся из поля «Длительность» формы (закрытый список
`LESSON_DURATIONS`), поэтому значения из слота не могут нарушить CHECK.

Защита от «бесконечной» серии: пустой список слотов, интервал меньше
недели и отсутствие даты окончания — ошибки; сверх того число дат
ограничено `MAX_SERIES_OCCURRENCES`.
"""

from datetime import date, datetime, time, timedelta

# Разумный потолок: ~10 лет еженедельных уроков. Серии длиннее —
# ошибка валидации, а не многотысячный цикл генерации.
MAX_SERIES_OCCURRENCES = 520


def _parse_time(raw: object, *, slot_index: int) -> time:
    """Время слота «HH:MM» (или уже `time`); иначе — ValueError."""
    if isinstance(raw, time):
        return raw
    if isinstance(raw, str):
        try:
            return time.fromisoformat(raw.strip())
        except ValueError:
            pass
    raise ValueError(f"Слот №{slot_index + 1}: время начала указано некорректно.")


def _parse_weekday(raw: object, *, slot_index: int) -> int:
    """День недели слота: целое 0..6 (0 — понедельник)."""
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(
            f"Слот №{slot_index + 1}: день недели должен быть числом 0–6."
        )
    if not 0 <= raw <= 6:
        raise ValueError(f"Слот №{slot_index + 1}: день недели вне диапазона 0–6.")
    return raw


def generate_occurrences(
    starts_at: datetime,
    slots: list[dict],
    interval_weeks: int,
    until_date: date | None,
) -> list[datetime]:
    """Даты уроков серии: начало каждого слота, пока не истечёт дата окончания.

    Первое вхождение слота — ближайший его день недели, не раньше
    `starts_at.date()`; далее — через `interval_weeks` недель, включая
    сам `until_date`. Часовой пояс результата — как у `starts_at`
    (naive остаётся naive).

    `ValueError` — пустой список слотов, интервал меньше недели,
    отсутствующая дата окончания, некорректный слот или слишком длинная
    серия.
    """
    if not slots:
        raise ValueError("Панель расписания пуста: добавьте хотя бы один слот.")
    if until_date is None:
        raise ValueError("Укажите дату окончания повтора.")
    if interval_weeks < 1:
        raise ValueError("Интервал повтора — не менее одной недели.")

    occurrences: list[datetime] = []
    for index, slot in enumerate(slots):
        weekday = _parse_weekday(slot.get("weekday"), slot_index=index)
        start_time = _parse_time(slot.get("start_time"), slot_index=index)
        # Ближайший день недели слота, не раньше даты начала.
        cursor = starts_at.date() + timedelta(days=(weekday - starts_at.weekday()) % 7)
        while cursor <= until_date:
            occurrences.append(
                datetime.combine(cursor, start_time, tzinfo=starts_at.tzinfo)
            )
            if len(occurrences) > MAX_SERIES_OCCURRENCES:
                raise ValueError(
                    "Серия слишком длинная: сократите дату окончания "
                    "или увеличьте интервал повтора."
                )
            cursor += timedelta(weeks=interval_weeks)
    return occurrences
