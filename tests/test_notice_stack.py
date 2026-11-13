"""Сводная плашка «Требует внимания · N» над несколькими предупреждениями.

Когда предупреждений вверху кабинета два и больше, вместо стопки плашек
показывается одна сводка с действием «Показать»/«Свернуть». Сервер о
количестве плашек не знает (их приносят независимые htmx-партиалы уже после
отрисовки страницы), поэтому счётчик, скрытие и раскрытие живут на клиенте:
Alpine-фабрика `noticeGroup` в `notices.js`.

Проверяется через HTTP тем же путём, что у пользователя: контейнер на
страницах кабинета и ответы партиалов. Клиентская часть проверяется по
содержимому `notices.js` — контракт (ключ состояния, наблюдатель за
htmx-свопами) фиксируется строкой, как и остальные Alpine-фабрики проекта.
"""

import re
from datetime import timedelta
from pathlib import Path

import pytest

from app.tutor.services.clock import utcnow

PASSWORD = "Секретный-Пароль-1"

ROOT = Path(__file__).resolve().parent.parent
NOTICES_JS = (ROOT / "app" / "static" / "notices.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")


def _login(client, tutor_factory, email: str, name: str = "Репетитор") -> str:
    """Создаёт репетитора и входит под ним; возвращает id."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": email, "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _stack(html: str) -> str:
    """Разметка группы плашек `#tutor-notice-stack` (вместе с содержимым)."""
    start = html.find('id="tutor-notice-stack"')
    assert start != -1, "на странице нет группы плашек"
    # Группа — последний блок `_notice_banner.html`: берём всё до закрытия
    # `main__container` не нужно, достаточно содержимого до конца вставки.
    return html[start:]


def test_group_markup_on_cabinet_pages(client, tutor_factory, student_factory):
    """На страницах кабинета есть сводка и оба контейнера внутри группы."""
    tutor_id = _login(client, tutor_factory, "stack-pages@example.com")
    student_id = student_factory(tutor_id=tutor_id)
    for url in (
        "/tutor/",
        "/tutor/students",
        "/tutor/lessons",
        "/tutor/calendar",
        "/tutor/groups",
        "/tutor/finance",
        "/tutor/profile",
        f"/tutor/students/{student_id}",
    ):
        stack = _stack(client.get(url).text)
        assert 'x-data="noticeGroup"' in stack, url
        # Сводка показывается только при двух и более видимых плашках.
        assert 'x-show="count > 1"' in stack, url
        assert "Требует внимания" in stack, url
        assert "Показать" in stack, url
        assert "Свернуть" in stack, url
        # Плашки — внутри скрываемого контейнера группы, а не рядом с ним:
        # свёртка прячет контейнер, поэтому счётчик не обнуляется.
        assert 'class="notice-stack__items"' in stack, url
        items = stack[stack.index('class="notice-stack__items"') :]
        assert 'id="tutor-balance-notice"' in items, url
        assert 'id="tutor-notices"' in items, url
        # Сводка остаётся на месте при раскрытии — она вне скрываемого блока.
        assert stack.index('class="notice-summary"') < stack.index(
            'class="notice-stack__items"'
        ), url


def _opening_tag(html: str, marker: str) -> str:
    """Открывающий тег, содержащий маркер (первый `>` внутри кавычек не в счёт)."""
    start = html.index(marker)
    start = html.rindex("<", 0, start)
    end = start
    quote = None
    while end < len(html):
        char = html[end]
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == ">":
            return html[start : end + 1]
        end += 1
    raise AssertionError("незакрытый тег")


def test_stack_hides_only_without_js_summary(client, tutor_factory):
    """`x-cloak` есть у сводки и нет у контейнера с плашками.

    Без `x-cloak` на контейнере одиночная плашка видна сразу, даже пока
    Alpine не загрузился; сводка же до инициализации не должна мелькать.
    """
    _login(client, tutor_factory, "stack-cloak@example.com")
    stack = _stack(client.get("/tutor/").text)

    assert "x-cloak" in _opening_tag(stack, 'class="notice-summary"')

    items = _opening_tag(stack, 'class="notice-stack__items"')
    assert "x-cloak" not in items
    assert 'x-show="count < 2 || expanded"' in items


def test_summary_markup_has_counter_and_toggle(client, tutor_factory):
    """Счётчик и действие сводки: `Требует внимания · N   Показать`."""
    _login(client, tutor_factory, "stack-markup@example.com")
    stack = _stack(client.get("/tutor/").text)

    assert 'class="notice-summary__count" x-text="count"' in stack
    assert "x-text=\"expanded ? 'Свернуть' : 'Показать'\"" in stack
    # Стрелка поворачивается при раскрытии, чтобы направление читалось.
    assert "notice-summary__chevron--open" in stack
    assert 'data-lucide="triangle-alert"' in stack
    assert 'data-lucide="chevron-down"' in stack


def test_js_factory_contract():
    """Клиентская часть: фабрика, ключ состояния и наблюдатель за свопами."""
    assert 'Alpine.data("noticeGroup"' in NOTICES_JS
    # Состояние раскрытия переживает перезагрузку и переходы между разделами.
    assert "opentutorcrm:notices-expanded" in NOTICES_JS
    # Плашки приходят htmx-свопами уже после отрисовки страницы.
    assert "MutationObserver" in NOTICES_JS
    assert "subtree: true" in NOTICES_JS
    # Счётчик считает видимые плашки, а не все подряд.
    assert 'querySelectorAll(".notice-banner")' in NOTICES_JS
    assert 'style.display !== "none"' in NOTICES_JS
    # Наблюдатель отключается вместе с компонентом (иначе утечка на переходах).
    assert "disconnect()" in NOTICES_JS


def test_summary_styles_are_described():
    """Каждый класс сводки из шаблона описан в styles.css плоским BEM."""
    for name in (
        "notice-summary",
        "notice-summary__icon",
        "notice-summary__title",
        "notice-summary__dot",
        "notice-summary__count",
        "notice-summary__toggle",
        "notice-summary__chevron",
        "notice-summary__chevron--open",
        "notice-stack__items",
    ):
        assert f".{name}" in STYLES, name
    # Узкий экран: счётчик и кнопка переносятся, а не сжимаются в никуда.
    block = re.search(r"\.notice-summary\s*\{([^}]*)\}", STYLES)
    assert block, "в styles.css нет правила .notice-summary"
    assert "flex-wrap: wrap" in block.group(1)


def _banners(html: str) -> int:
    """Сколько плашек в ответе партиала (`class="notice-banner"` + модификатор)."""
    return len(re.findall(r'class="notice-banner(?:\s|")', html))


def test_partials_keep_single_banner_markup(
    client, tutor_factory, student_factory, lesson_factory
):
    """Партиалы отдают ровно одну плашку и не знают про сводку.

    Состав и тексты предупреждений не меняются, а серверное состояние
    раскрытия не вводится: сводка — чисто клиентская обёртка страницы.
    Урок прошедший и на сегодня, поэтому оба предупреждения настоящие.
    """
    tutor_id = _login(client, tutor_factory, "stack-partials@example.com")
    student_id = student_factory(tutor_id=tutor_id, first_name="Иван")
    lesson_factory(
        student_id=student_id,
        status="planned",
        starts_at=utcnow() - timedelta(hours=1),
        duration_min=60,
    )

    unmarked = client.get("/tutor/notices").text
    assert _banners(unmarked) == 1
    assert "1 урок не отмечен" in unmarked
    assert "Требует внимания" not in unmarked
    assert "notice-summary" not in unmarked

    balance = client.get("/tutor/notices/balance").text
    assert _banners(balance) == 1
    assert "Сегодня занятие у 1 ученика" in balance
    assert "Требует внимания" not in balance
    assert "notice-summary" not in balance


def test_partials_empty_when_nothing_to_show(client, tutor_factory):
    """Нет предупреждений — оба партиала отвечают пустым телом."""
    _login(client, tutor_factory, "stack-empty@example.com")

    assert client.get("/tutor/notices").text == ""
    assert client.get("/tutor/notices/balance").text == ""


@pytest.mark.parametrize(
    "url", ["/tutor/notices", "/tutor/notices/balance"]
)
def test_partials_require_session(client, url):
    """Без сессии партиалы недоступны: редирект на вход."""
    response = client.get(url, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
