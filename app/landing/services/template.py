"""Шаблон лендинга по умолчанию: контекст из профиля и рендер черновика.

Лендинг создаётся из данных репетитора (`Tutor`): имя, предмет, «О себе»,
опыт, ставка и телефон. Формы заявки нет — CTA «Записаться на занятие»
ведёт на существующую публичную страницу `/s/<tutor_id>` (ссылка строится
по образцу `app/slot/services/public_link.py`, без новой семантики).

Шаблон `landing/default_page.html.j2` самодостаточен: CSS внутри файла,
никаких CDN и общего `app.css`. Это важно, потому что опубликованная
страница отдаётся как обычный файл с `/`, без рендера и без доступа к
статике приложения (кроме картинок редактора).

Расширение `.j2` не входит в `select_autoescape` Jinja, поэтому все поля
профиля в шаблоне экранируются явно (`| e`): иначе `<script>` из «О себе»
стал бы исполняемым на публичной странице.
"""

from decimal import Decimal

from app.landing.services.storage import LandingStorage, get_storage
from app.slot.services.public_link import PUBLIC_PREFIX
from app.tutor.models.tutor import Tutor

# Имя шаблона страницы по умолчанию. Файл лежит в корне каталога шаблонов
# модуля (`app/landing/templates/default_page.html.j2`); шаблоны интерфейса
# модуля неймспейсятся подкаталогом (`landing/page.html`).
DEFAULT_TEMPLATE = "default_page.html.j2"

# Статусы страницы управления: публикация приоритетнее черновика — если
# страница уже на сайте, репетитору важнее видеть именно это.
STATUS_PUBLISHED = "published"
STATUS_DRAFT = "draft"
STATUS_EMPTY = "empty"


def public_page_url(tutor_id: str) -> str:
    """Адрес публичной страницы записи этого репетитора: `/s/<tutor_id>`."""
    return f"{PUBLIC_PREFIX}/{tutor_id}"


def hourly_rate_label(value: Decimal | int | float | None) -> str:
    """Ставка для лендинга: «1 200 ₽»; нет значения — пустая строка.

    Разделитель разрядов — неразрывный пробел, как в остальных ценах
    проекта: число не переносится отдельно от знака рубля. Копейки
    показываются только если они есть — «1 200 ₽», а не «1 200,00 ₽».
    """
    if value is None:
        return ""
    amount = Decimal(str(value))
    if amount == amount.to_integral_value():
        number = f"{int(amount):,}".replace(",", "\u00a0")
    else:
        number = (
            f"{amount:,.2f}".replace(",", "\u00a0").replace(".", ",")
        )
    return f"{number}\u00a0₽"


def phone_href(value: str | None) -> str:
    """Значение `tel:` для телефона: только цифры и ведущий плюс.

    Профиль хранит телефон свободным текстом («+7 (999) 999-99-99»), а в
    `href` нужен компактный вид без пробелов и скобок — иначе часть
    браузеров не распознаёт ссылку как номер.
    """
    if not value:
        return ""
    digits = "".join(ch for ch in value if ch.isdigit() or ch == "+")
    return digits


def page_title(tutor: Tutor) -> str:
    """`<title>` лендинга: «{имя} — репетитор по {предмету}».

    Без предмета — «{имя} — репетитор»: пустой хвост «по » читался бы
    как обрывок.
    """
    name = (tutor.name or "").strip()
    subject = (tutor.subject or "").strip()
    if subject:
        return f"{name} — репетитор по {subject}"
    return f"{name} — репетитор"


def build_default_context(tutor: Tutor) -> dict:
    """Контекст шаблона по умолчанию из профиля репетитора.

    Пустые поля остаются пустыми строками: шаблон сам решает, рисовать ли
    секцию, и в разметку не попадает «None».
    """
    return {
        "title": page_title(tutor),
        "name": (tutor.name or "").strip(),
        "subject": (tutor.subject or "").strip(),
        "about": (tutor.about or "").strip(),
        "experience": (tutor.experience or "").strip(),
        "rate": hourly_rate_label(tutor.hourly_rate),
        "phone": (tutor.phone or "").strip(),
        "phone_href": phone_href(tutor.phone),
        "cta_url": public_page_url(tutor.id),
    }


def render_default_page(tutor: Tutor) -> str:
    """HTML страницы по умолчанию для этого репетитора."""
    from app.templating import templates

    template = templates.env.get_template(DEFAULT_TEMPLATE)
    return template.render(**build_default_context(tutor))


def save_default_draft(tutor: Tutor) -> str:
    """Перезаписывает черновик шаблоном из профиля и возвращает HTML.

    Вызывается только явным действием «Вернуть шаблон» (или созданием
    первого черновика): обычный просмотр страницы управления черновик не
    трогает, иначе правки редактора терялись бы при каждом открытии.
    """
    html = render_default_page(tutor)
    get_storage().save_draft(html)
    return html


def page_state(storage: LandingStorage) -> dict:
    """Состояние лендинга для страницы управления.

    `published` — страница на сайте, `draft` — есть только черновик,
    `empty` — нет ни того, ни другого. Публикация приоритетнее: при
    опубликованной странице репетитору важно видеть её статус, даже если
    черновик уже правился.
    """
    published = storage.has_published()
    has_draft = storage.has_draft()
    if published:
        status = STATUS_PUBLISHED
    elif has_draft:
        status = STATUS_DRAFT
    else:
        status = STATUS_EMPTY
    return {"published": published, "has_draft": has_draft, "status": status}


def register_template_helpers() -> None:
    """Регистрирует `landing_enabled` в общем Jinja-окружении.

    Сайдбар включает пункт «Лендинг» только в сингл-режиме, а флаг живёт
    в сервисе доступа: регистрируем его глобально, чтобы не передавать в
    контекст каждой страницы, включающей сайдбар.
    """
    from app.landing.services.access import landing_enabled
    from app.templating import templates

    templates.env.globals.update(landing_enabled=landing_enabled)
