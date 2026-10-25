"""Тесты страницы статистики (`/tutor/stats`).

Поведение проверяется тем же путём, что у пользователя: те же маршруты и
query-параметры, разметка ищется по тексту и атрибутам. Даты строятся от
«сейчас» (зона репетитора в тестах — UTC): прибитые к октябрю 2026 тесты
сломались бы в следующем месяце.

Ключевой сценарий (метрики обзора): Аня и Борис занимались за 14 дней,
Вера в архиве (ушла), Гоша молча перестал ходить (риск), Даша ходила только
на пробное — учебной активностью не считается.
"""

import re
from datetime import timedelta

from app.tutor.services.clock import utcnow

# Неразрывный пробел форматтера денег: «2 000 ₽» пишется без обычных пробелов.
NBSP = "\u00a0"

PASSWORD = "Секретный-Пароль-1"


def _login(client, tutor_factory, email="stats@example.com", name="Статист", **extra):
    """Репетитор с заводской карточкой (зона UTC) и вход под ним."""
    tutor_id = tutor_factory(name=name, email=email, password=PASSWORD, **extra)
    client.post("/tutor/login", data={"email": email, "password": PASSWORD})
    return tutor_id


def _kpi_value(html: str, title: str) -> str:
    """Значение KPI-карточки по её заголовку (блок: заголовок → число)."""
    match = re.search(
        rf'{re.escape(title)}</span>.*?stats-kpi__value">\s*([^<]*?)\s*</p>',
        html,
        flags=re.S,
    )
    assert match, f"нет KPI-карточки «{title}»"
    return match.group(1).strip()


def _duo_value(html: str, label: str) -> str:
    """Значение парной карточки («Заведено»/«Стали активными») по подписи."""
    match = re.search(
        rf'{re.escape(label)}</p>.*?stats-duo__value">\s*(\d+)\s*<',
        html,
        flags=re.S,
    )
    assert match, f"нет карточки «{label}»"
    return match.group(1)


def test_redirect_to_login_without_session(client):
    for path in ("/tutor/stats", "/tutor/stats/students.csv"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/tutor/login"


def test_overview_empty(client, tutor_factory):
    _login(client, tutor_factory)
    response = client.get("/tutor/stats")
    html = response.text
    assert response.status_code == 200
    assert "Статистика и Аналитика" in html
    assert "Ученики (0)" in html
    assert _kpi_value(html, "LTV (Сред. чек)") == "—"
    assert _kpi_value(html, "Retention Rate") == "—"
    assert _kpi_value(html, "Активных") == "0"
    assert _kpi_value(html, "Потерянных") == "0"
    assert "Риск потери: 0" in html
    assert "Все активные ученики посещают занятия регулярно!" in html


def test_overview_metrics(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    now = utcnow()
    tutor_id = _login(client, tutor_factory)

    # Аня: занималась вчера, платила 2000; при этом 2 занятия за 4 недели.
    anna_id = student_factory(tutor_id=tutor_id, first_name="Аня", status="active")
    lesson_factory(
        student_id=anna_id, starts_at=now - timedelta(days=1), price=1200
    )
    lesson_factory(
        student_id=anna_id, starts_at=now - timedelta(days=10), price=1200
    )
    operation_factory(student_id=anna_id, amount=2000, occurred_at=now)

    boris_id = student_factory(tutor_id=tutor_id, first_name="Борис", status="active")
    lesson_factory(student_id=boris_id, starts_at=now - timedelta(days=2), price=1200)

    vera_id = student_factory(tutor_id=tutor_id, first_name="Вера", status="archived")
    lesson_factory(
        student_id=vera_id, starts_at=now - timedelta(days=40, hours=2), price=1200
    )

    gosha_id = student_factory(tutor_id=tutor_id, first_name="Гоша", status="active")
    lesson_factory(student_id=gosha_id, starts_at=now - timedelta(days=40), price=1200)

    # Даша: единственное занятие — пробное; в активность не считается.
    dasha_id = student_factory(tutor_id=tutor_id, first_name="Даша", status="active")
    lesson_factory(
        student_id=dasha_id,
        type="trial",
        starts_at=now - timedelta(days=1),
        price=0,
    )

    response = client.get("/tutor/stats")
    assert response.status_code == 200
    html = response.text

    assert _kpi_value(html, "Активных") == "2"
    assert _kpi_value(html, "Потерянных") == "1"
    # Занимались четверо, статусно-активных из них трое.
    assert _kpi_value(html, "Retention Rate") == "75%"
    # Выручка 2000 на четверых занимавшихся.
    assert "500" in _kpi_value(html, "LTV (Сред. чек)")
    # Пробное Даши не создало ни активности, ни риска.
    assert "Риск потери: 1" in html
    risk_block = html[html.index("Риск потери:") :]
    assert "Гоша" in risk_block
    assert "Даша" not in risk_block
    assert "Все активные ученики посещают занятия регулярно!" not in html


def test_students_tab_filters_and_sorting(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    now = utcnow()
    tutor_id = _login(client, tutor_factory)

    anna_id = student_factory(tutor_id=tutor_id, first_name="Аня", status="active")
    lesson_factory(student_id=anna_id, starts_at=now - timedelta(days=1), price=1200)
    lesson_factory(student_id=anna_id, starts_at=now - timedelta(days=10), price=1200)
    operation_factory(student_id=anna_id, amount=2000, occurred_at=now)
    # Будущее занятие: с фильтром «Без будущих занятий» Аня исчезнет.
    lesson_factory(
        student_id=anna_id,
        status="planned",
        starts_at=now + timedelta(days=1),
        price=1200,
    )

    boris_id = student_factory(tutor_id=tutor_id, first_name="Борис", status="active")
    lesson_factory(student_id=boris_id, starts_at=now - timedelta(days=2), price=1200)

    vera_id = student_factory(tutor_id=tutor_id, first_name="Вера", status="archived")
    lesson_factory(
        student_id=vera_id, starts_at=now - timedelta(days=40, hours=2), price=1200
    )

    gosha_id = student_factory(tutor_id=tutor_id, first_name="Гоша", status="active")
    lesson_factory(student_id=gosha_id, starts_at=now - timedelta(days=40), price=1200)

    page = client.get("/tutor/stats?tab=students")
    assert page.status_code == 200
    html = page.text

    # Сортировка по дате последнего занятия: свежие сверху; Гоша (40 дней
    # назад) раньше Веры (то же, но на два часа старее).
    assert html.index("Аня") < html.index("Борис") < html.index("Гоша")
    assert html.index("Гоша") < html.index("Вера")

    # Состояния активности и подсказка «Занятий/нед» (2 занятия за 4 недели).
    assert "Активен" in html
    assert "Отвалился" in html
    assert "Ушёл" in html
    assert "0,5" in html
    assert f"2{NBSP}000" in html  # баланс Ани
    assert "Всего: 4" in html
    assert "страница 1 из 1" in html

    # Фильтр активности: активные — без ушедшей Веры и отвалившегося Гоши.
    filtered = client.get("/tutor/stats?tab=students&activity=active").text
    assert "Аня" in filtered and "Борис" in filtered
    assert "Вера" not in filtered and "Гоша" not in filtered

    assert "Вера" in client.get("/tutor/stats?tab=students&activity=lost").text
    assert "Аня" not in client.get("/tutor/stats?tab=students&activity=lost").text

    risk_page = client.get("/tutor/stats?tab=students&activity=risk").text
    assert "Гоша" in risk_page and "Аня" not in risk_page

    archived = client.get("/tutor/stats?tab=students&status=archived").text
    assert "Вера" in archived and "Борис" not in archived

    search = client.get("/tutor/stats?tab=students&q=Борис").text
    assert "Борис" in search and "Аня" not in search

    # «Без будущих занятий»: у Ани занятие запланировано — её в списке нет.
    no_future = client.get("/tutor/stats?tab=students&no_future=1").text
    assert "Гоша" in no_future
    assert "Аня" not in no_future


def test_students_csv(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    now = utcnow()
    tutor_id = _login(client, tutor_factory)

    anna_id = student_factory(tutor_id=tutor_id, first_name="Аня", status="active")
    lesson_factory(student_id=anna_id, starts_at=now - timedelta(days=1), price=1200)
    operation_factory(student_id=anna_id, amount=2000, occurred_at=now)

    vera_id = student_factory(tutor_id=tutor_id, first_name="Вера", status="archived")
    lesson_factory(student_id=vera_id, starts_at=now - timedelta(days=40), price=1200)

    response = client.get("/tutor/stats/students.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    body = response.content.decode("utf-8-sig")
    assert body.splitlines()[0].startswith("Имя;Педагог;Статус")
    assert "Аня" in body and "Вера" in body
    assert "2000" in body  # баланс без форматирования
    assert "0,2" in body  # Аня: 1 занятие за 4 недели (округление до одной цифры)

    # Фильтры применяются так же, как во вкладке.
    lost = client.get("/tutor/stats/students.csv?activity=lost")
    lost_body = lost.content.decode("utf-8-sig")
    assert "Вера" in lost_body and "Аня" not in lost_body


def test_new_and_trials_tab(
    client, tutor_factory, student_factory, lesson_factory, operation_factory
):
    now = utcnow()
    tutor_id = _login(client, tutor_factory)

    # Заведены сегодня; Аня сегодня же и оплатила (первый платёж).
    anna_id = student_factory(tutor_id=tutor_id, first_name="Аня", status="active")
    operation_factory(student_id=anna_id, amount=2000, occurred_at=now)

    boris_id = student_factory(tutor_id=tutor_id, first_name="Борис", status="new")

    # Конверсия: у Ани после пробного (вчера) было обычное занятие — осталась;
    # у Бориса после пробного ничего — не засчитан.
    lesson_factory(
        student_id=anna_id, type="trial", starts_at=now - timedelta(days=1), price=0
    )
    lesson_factory(student_id=anna_id, starts_at=now, price=1200)
    lesson_factory(
        student_id=boris_id, type="trial", starts_at=now - timedelta(days=1), price=0
    )

    page = client.get("/tutor/stats?tab=new")
    assert page.status_code == 200
    html = page.text

    assert "Заведено" in html and "Стали активными" in html
    assert _duo_value(html, "Заведено") == "2"
    assert _duo_value(html, "Стали активными") == "1"
    assert "Статист" in html  # разбивка по педагогу — владелец аккаунта
    assert "мало данных" in html  # 2 пробных — меньше порога
    assert "Сверка: пробных всего 2 =" in html
    assert "не засчитано 1" in html
    assert "есть занятие после пробного" in html
    assert "не остался: занятий и оплат после пробного нет" in html


def test_new_tab_period_filter(
    client, tutor_factory, student_factory, operation_factory
):
    now = utcnow()
    tutor_id = _login(client, tutor_factory)

    # Старая карточка: создана 100 дней назад и тогда же оплачена.
    old_id = student_factory(
        tutor_id=tutor_id,
        first_name="Старая",
        created_at=now - timedelta(days=100),
    )
    operation_factory(
        student_id=old_id, amount=2000, occurred_at=now - timedelta(days=100)
    )
    student_factory(tutor_id=tutor_id, first_name="Свежая")

    # Вкладка показывает счётчики, а не имена: старая карточка (100 дней
    # назад) не попадает в «Сегодня» и «30 дней».
    today_page = client.get("/tutor/stats?tab=new&period=today")
    assert _duo_value(today_page.text, "Заведено") == "1"
    assert _duo_value(today_page.text, "Стали активными") == "0"

    month_page = client.get("/tutor/stats?tab=new&period=30d")
    assert _duo_value(month_page.text, "Заведено") == "1"

    # Произвольный включительный диапазон захватывает старую карточку и её
    # первую оплату.
    custom = client.get(
        "/tutor/stats?tab=new&period=custom"
        f"&date_from={(now - timedelta(days=100)):%Y-%m-%d}"
        f"&date_to={now:%Y-%m-%d}"
    )
    assert _duo_value(custom.text, "Заведено") == "2"
    assert _duo_value(custom.text, "Стали активными") == "1"

    # Мусорные даты — не 500, а «Всё время» (обе карточки).
    garbage = client.get("/tutor/stats?tab=new&period=custom&date_from=xx&date_to=yy")
    assert garbage.status_code == 200
    assert _duo_value(garbage.text, "Заведено") == "2"


def test_forecast_on_overview(
    client, tutor_factory, student_factory, lesson_factory, group_factory,
    group_member_factory,
):
    now = utcnow()
    tutor_id = _login(client, tutor_factory)

    anna_id = student_factory(tutor_id=tutor_id, first_name="Аня", status="active")
    lesson_factory(
        student_id=anna_id,
        status="planned",
        starts_at=now + timedelta(days=1),
        price=1500,
    )

    group_id = group_factory(tutor_id=tutor_id, price_per_lesson=500)
    boris_id = student_factory(tutor_id=tutor_id, first_name="Борис", status="active")
    group_member_factory(group_id=group_id, student_id=boris_id)
    lesson_factory(
        group_id=group_id,
        status="planned",
        starts_at=now + timedelta(days=2),
        price=None,
    )
    # Проведённый урок и урок за горизонтом в прогноз не попадают.
    lesson_factory(student_id=anna_id, starts_at=now - timedelta(days=1), price=1200)
    lesson_factory(
        student_id=anna_id,
        status="planned",
        starts_at=now + timedelta(days=40),
        price=1200,
    )

    page = client.get("/tutor/stats?tab=overview&forecast=1")
    assert page.status_code == 200
    assert "Прогноз на месяц" in page.text
    assert f"2{NBSP}000" in page.text  # 1500 (Аня) + 500 (Борис, цена группы)
    assert "Запланировано занятий" in page.text

    # Без параметра прогноз не считается и не показывается.
    plain = client.get("/tutor/stats")
    assert "Ожидаемая выручка" not in plain.text


def test_isolation_between_tutors(
    client, tutor_factory, student_factory, lesson_factory
):
    _login(client, tutor_factory, email="owner@example.com", name="Владелец")
    other_tutor = tutor_factory(name="Чужой", email="other@example.com")
    other_id = student_factory(
        tutor_id=other_tutor, first_name="ЧужойУченик", status="active"
    )
    lesson_factory(student_id=other_id)

    for path in (
        "/tutor/stats",
        "/tutor/stats?tab=students",
        "/tutor/stats?tab=new",
        "/tutor/stats/students.csv",
    ):
        response = client.get(path)
        assert response.status_code == 200
        content = response.content.decode("utf-8-sig")
        assert "ЧужойУченик" not in content
        assert "Чужой" not in content


def test_unknown_tab_falls_back_to_overview(client, tutor_factory):
    _login(client, tutor_factory)
    response = client.get("/tutor/stats?tab=bogus")
    assert response.status_code == 200
    assert "LTV (Сред. чек)" in response.text
