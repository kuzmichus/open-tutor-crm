"""Отображение файлов: размер в человекочитаемом виде.

Чистые функции без БД и HTTP (как остальные `presentation.py` проекта).
Русский формат: запятая как десятичный разделитель, единицы «КБ»/«МБ» —
как в макете списка файлов. Байты показываются целыми: «512 Б».
"""

# Порог перехода к следующей единице — 1024, как в файловых менеджерах.
_UNITS = ("Б", "КБ", "МБ", "ГБ")

def file_size_label(size: int | None) -> str:
    """Размер файла: «512 Б», «12,4 КБ», «3,1 МБ»."""
    if not size or size < 0:
        return "0 Б"

    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(_UNITS) - 1:
        value /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(value)} Б"
    # Один знак после запятой: «12,4 КБ» — точности хватает, лишние
    # нули не нужны («3,0 МБ» читается хуже, чем «3 МБ»).
    text = f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{text} {_UNITS[unit_index]}"

def file_download_name(name: str) -> str:
    """Имя для показа в списке: как есть, но пустое имя — «Файл»."""
    return (name or "").strip() or "Файл"

def register_template_helpers() -> None:
    """Регистрирует функции отображения в общем Jinja-окружении."""
    from app.templating import templates

    templates.env.globals.update(
        file_size_label=file_size_label,
        file_download_name=file_download_name,
    )
