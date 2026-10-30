"""Фокус-ловушка модальных диалогов (`modal.js`).

Диалоги приходят htmx-свопом в разные контейнеры и закрываются Alpine'ом,
поэтому ловушка живёт одним наблюдателем за DOM, а не методом каждой
формы. Задача P1 критики: `aria-modal="true"` обещал изоляцию фона, а
первый же Tab уводил в карточки под оверлеем.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
BASE_HTML = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
MODAL_JS = (STATIC_DIR / "modal.js").read_text(encoding="utf-8")

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="modal-focus@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "modal-focus@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


# --------------------------------------------------------------------------
# Подключение
# --------------------------------------------------------------------------


def test_modal_js_is_loaded_after_alpine_before_app():
    """После Alpine (наблюдательу нужен работающий DOM) и до app.js."""
    assert '/static/modal.js' in BASE_HTML
    assert BASE_HTML.index("/static/alpine.min.js") < BASE_HTML.index(
        "/static/modal.js"
    )
    assert BASE_HTML.index("/static/modal.js") < BASE_HTML.index("/static/app.js")


def test_modal_js_asset_is_served(client):
    response = client.get("/static/modal.js")
    assert response.status_code == 200
    assert "inert" in response.text


def test_dialogs_declare_aria_modal(client, owner, group_factory):
    """Обещание, которое ловушка делает правдой, есть в разметке."""
    group_id = group_factory(tutor_id=owner, name="A")
    for markup in (
        client.get("/tutor/students/new").text,
        client.get(f"/tutor/groups/{group_id}/edit").text,
    ):
        assert 'role="dialog"' in markup
        assert 'aria-modal="true"' in markup


# --------------------------------------------------------------------------
# Поведение модуля
# --------------------------------------------------------------------------


def test_background_is_isolated_along_ancestor_chain():
    """Изоляция идёт по цепочке предков, а не только по детям `body`.

    Контейнер `#modal` лежит внутри `.main`: если гасить лишь соседей
    `body`, карточки учеников под оверлеем остаются в фокусе — это и был
    исходный дефект критики.
    """
    isolate = re.search(r"function isolate\(dialog\)[\s\S]*?\n  \}", MODAL_JS)
    assert isolate, "модуль не изолирует фон"
    body = isolate.group(0)
    assert "parentElement" in body
    assert "markInert(sibling)" in body
    assert "document.body" in body
    # Снимаем только то, что ставили сами: на странице бывают свои inert.
    assert "element.hasAttribute(\"inert\")" in MODAL_JS
    assert "inerted.push(element)" in MODAL_JS


def test_top_dialog_is_chosen_by_layer():
    """Вложенный слой (счёт поверх карточки) всегда выигрывает у нижнего."""
    assert "function topDialog()" in MODAL_JS
    assert ".modal-content[role='dialog']" in MODAL_JS
    assert "layerZIndex" in MODAL_JS
    assert ".modal-root" in MODAL_JS


def test_tab_is_cycled_inside_dialog():
    """Tab/Shift+Tab зациклены; фокус вне диалога возвращается внутрь."""
    listener = re.search(
        r'addEventListener\("keydown",\s*function \(event\)[\s\S]*?\n  \}\);', MODAL_JS
    )
    assert listener, "нет обработчика Tab"
    body = listener.group(0)
    assert 'event.key !== "Tab"' in body
    assert "event.shiftKey" in body
    assert "preventDefault()" in body
    assert "activeDialog.contains(current)" in body


def test_focus_returns_to_the_opener():
    """После закрытия фокус возвращается туда, откуда диалог открыли."""
    assert "returnFocusTo" in MODAL_JS
    assert "document.activeElement" in MODAL_JS
    assert "target.isConnected" in MODAL_JS


def test_observer_watches_htmx_swaps():
    """Диалоги появляются свопом и исчезают очисткой — единого события нет."""
    assert "new MutationObserver(sync)" in MODAL_JS
    assert "subtree: true" in MODAL_JS
    assert '"htmx:afterSwap"' in MODAL_JS
    assert '"DOMContentLoaded"' in MODAL_JS


def test_autofocus_is_not_overridden():
    """Если фокус уже в диалоге (клик по полю), его не перебиваем."""
    assert "dialog.contains(document.activeElement)" in MODAL_JS
    assert 'querySelector("[autofocus]")' in MODAL_JS
