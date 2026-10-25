"""CSV-выгрузка вкладки «Ученики»: те же строки, что в таблице, без пагинации.

UTF-8 с BOM и разделитель «;» — файл открывается в Excel с кириллицей двойным
кликом, без мастера импорта (design D9). Числа пишутся без форматирования
(неразрывные пробелы в деньгах сломали бы разбор), даты — в зоне педагога.
"""

import csv
from io import StringIO

from app.student.services.presentation import (
    next_lesson_label,
    short_date_label,
    status_label,
    student_full_name,
)
from app.stats.services.presentation import week_rate_label
from app.stats.services.student_rows import ACTIVITY_LABELS

# Заголовок выгрузки. Названия колонок совпадают с таблицей вкладки.
CSV_HEADERS = (
    "Имя",
    "Педагог",
    "Статус",
    "Активность",
    "Цена занятия",
    "Баланс",
    "Занятий/нед",
    "Последнее",
    "Следующее",
    "Email",
    "Телефон",
    "Создан",
)


def students_csv_text(rows: list[dict], tutor) -> str:
    """CSV-текст списка учеников; BOM добавляется вызывающей стороной записи."""
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(CSV_HEADERS)
    for row in rows:
        student = row["student"]
        writer.writerow(
            [
                student_full_name(student),
                tutor.name,
                status_label(student.status),
                ACTIVITY_LABELS.get(row["activity"], ""),
                row["last_price"] if row["last_price"] is not None else "",
                row["balance"],
                week_rate_label(row["week_count"]),
                short_date_label(row["last_lesson_at"], tutor),
                next_lesson_label(row["next_at"], tutor),
                student.email or "",
                student.phone or "",
                short_date_label(student.created_at, tutor),
            ]
        )
    return buffer.getvalue()
