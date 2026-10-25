"""Урок в блоке «Расписание на сегодня» главной страницы."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TodayLesson:
    """Строка расписания «на сегодня»: цель, подпись и границы урока.

    `starts_at`/`ends_at` — aware UTC, источник истины; настенное время
    зоны педагога выводит `time_range` на показе (спека tutor-timezone).
    `status` нужен странице и для строки, и для счётчика «Запланировано»:
    обе цифры главной считаются из одной выборки, а не двумя запросами.
    """

    starts_at: datetime
    ends_at: datetime
    name: str
    subtitle: str
    status: str
