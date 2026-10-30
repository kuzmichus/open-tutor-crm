"""Обратная связь при остановленной отправке формы (`form-feedback.js`).

Модуль родился из P1 критики: браузерная валидация не пускает запрос до
сервера, серверный блок `.error` не приходит, и человек видит только то,
что ничего не произошло. Здесь проверяется и подключение модуля, и то, что
каждая форма с вкладками умеет раскрыться до невалидного поля — иначе
сводка уедет в скрытую панель.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "app" / "static"
BASE_HTML = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
FEEDBACK = (STATIC_DIR / "form-feedback.js").read_text(encoding="utf-8")

PASSWORD = "Секретный-Пароль-1"


@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="form-feedback@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "form-feedback@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id


def _panel_tags(markup: str) -> list[str]:
    """Разметка каждой панели вкладки (тег может переноситься по строкам)."""
    return re.findall(r"<[^>]*data-tab-panel=\"[^\"]+\"[^>]*>", markup, flags=re.S)


def _assert_panels_point_to_tabs(markup: str) -> None:
    """Каждая панель названа тем табом, что её открывает.

    `form-feedback.js` раскрывает скрытую вкладку кликом по кнопке,
    найденной через `aria-labelledby` панели: без этой связи невалидное
    поле в скрытой панели останется невидимым.
    """
    tags = _panel_tags(markup)
    assert tags, "на странице нет панелей с data-tab-panel"
    for tag in tags:
        panel = re.search(r'data-tab-panel="([^"]+)"', tag).group(1)
        labelled = re.search(r'aria-labelledby="([^"]+)"', tag)
        assert labelled, f"панель {panel} не названа кнопкой вкладки"
        tab_id = labelled.group(1)
        button = re.search(rf"<[^>]*id=\"{re.escape(tab_id)}\"[^>]*>", markup, flags=re.S)
        assert button, f"кнопка {tab_id} для панели {panel} не найдена"
        assert 'role="tab"' in button.group(0), f"{tab_id} не кнопка вкладки"
        assert f"tab = '{panel}'" in button.group(0), (
            f"клик по {tab_id} не открывает панель {panel}"
        )


# --------------------------------------------------------------------------
# Подключение
# --------------------------------------------------------------------------


def test_form_feedback_is_loaded_locally_after_htmx():
    """Модуль подключён локально и после htmx: слушает его события."""
    assert '/static/form-feedback.js' in BASE_HTML
    assert BASE_HTML.index("/static/htmx.min.js") < BASE_HTML.index(
        "/static/form-feedback.js"
    )
    script_sources = re.findall(r'<script[^>]*\ssrc="([^"]+)"', BASE_HTML)
    assert all(src.startswith("/static/") for src in script_sources), script_sources


def test_form_feedback_asset_is_served(client):
    response = client.get("/static/form-feedback.js")
    assert response.status_code == 200
    assert "htmx:validation:halted" in response.text


def test_modal_focus_trap_is_loaded(client):
    """Фокус-ловушка и обратная связь — соседи: оба ждут DOM и события htmx."""
    assert '/static/modal.js' in BASE_HTML
    assert BASE_HTML.index("/static/modal.js") < BASE_HTML.index(
        "/static/form-feedback.js"
    )
    assert client.get("/static/modal.js").status_code == 200


# --------------------------------------------------------------------------
# Поведение модуля
# --------------------------------------------------------------------------


def test_invalid_is_listened_in_capture_phase():
    """`invalid` не всплывает — поймать его можно только перехватом."""
    listener = re.search(
        r'addEventListener\(\s*"invalid",\s*function[\s\S]*?\},\s*true\s*\)', FEEDBACK
    )
    assert listener, "слушатель invalid должен быть в фазе перехвата (true)"


def test_both_halting_paths_are_handled():
    """Браузер и htmx останавливают отправку по-разному — оба случая нужны."""
    assert '"htmx:validation:halted"' in FEEDBACK
    # htmx кладёт в detail форму и список `{elt, message}`.
    assert "detail.errors" in FEEDBACK
    assert "elt.tagName" in FEEDBACK


def test_summary_is_alert_and_links_fields():
    """Сводка — `.error[role=alert]`, поля ссылаются на неё через id."""
    assert 'summary.className = "error"' in FEEDBACK
    assert 'setAttribute("role", "alert")' in FEEDBACK
    assert 'setAttribute("aria-invalid", "true")' in FEEDBACK
    assert '"aria-describedby"' in FEEDBACK
    # Одинаковые сообщения не дублируются, у слоёв свой id.
    assert "var seen = {}" in FEEDBACK
    assert "summarySeq" in FEEDBACK


def test_summary_lands_in_visible_panel_body():
    """Сводка живёт в теле видимой панели, а не в скрытой форме вкладки."""
    assert 'target.closest(".modal-body")' in FEEDBACK
    # Область очистки — диалог целиком: форм в модалке несколько.
    assert 'closest("[role=\'dialog\']")' in FEEDBACK


def test_stale_summary_is_cleared():
    """Правка поля или ушедший запрос снимают устаревшее сообщение."""
    for trigger in ('"input"', '"change"', '"htmx:beforeRequest"'):
        assert trigger in FEEDBACK, f"нет очистки по событию {trigger}"
    assert 'removeAttribute("aria-invalid")' in FEEDBACK


def test_hidden_tab_is_revealed_before_focus():
    """Панель раскрывается тем табом, что её открывает, — до фокуса."""
    reveal = re.search(r"function revealPanel\(field\)[\s\S]*?\n  \}", FEEDBACK)
    assert reveal, "модуль не раскрывает скрытую панель"
    body = reveal.group(0)
    assert 'closest("[data-tab-panel]")' in body
    assert 'getAttribute("aria-labelledby")' in body
    assert 'getAttribute("role") !== "tab"' in body
    assert "tab.click()" in body
    # Фокус — следующим тиком: Alpine применяет x-show в микрозадаче.
    assert "setTimeout" in FEEDBACK


# --------------------------------------------------------------------------
# Разметка страниц: связь панель ↔ кнопка вкладки
# --------------------------------------------------------------------------


def test_student_form_panels_point_to_their_tabs(client, owner):
    markup = client.get("/tutor/students/new").text
    _assert_panels_point_to_tabs(markup)


def test_group_form_panels_point_to_their_tabs(client, owner, student_factory, group_factory):
    group_id = group_factory(tutor_id=owner, name="A")
    markup = client.get(f"/tutor/groups/{group_id}/edit").text
    _assert_panels_point_to_tabs(markup)


def test_group_form_is_one_form_for_all_panels(client, owner, group_factory):
    """Форма группы одна на пять панелей: невалидное поле может быть скрыто.

    Именно этот случай не покрывался раньше: браузер блокировал отправку,
    а вкладку с виновником никто не раскрывал.
    """
    group_id = group_factory(tutor_id=owner, name="B")
    markup = client.get(f"/tutor/groups/{group_id}/edit").text
    forms = re.findall(r"<form\b", markup)
    assert len(forms) == 1, "ожидалась одна форма на все вкладки"
    assert len(_panel_tags(markup)) >= 3
