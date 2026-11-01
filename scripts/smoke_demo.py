"""Смоук-проверка демо-данных: страницы приложения рендерятся без ошибок.

Запуск: `uv run python scripts/smoke_demo.py`

Проверяются и страницы-списки, и карточки конкретных сущностей из демо-базы:
данные с неявками, возвратами и должниками должны открываться так же, как
обычные. Скрипт ничего не пишет — только читает.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.group.models.group import Group  # noqa: E402
from app.student.models.student import Student  # noqa: E402
from app.task.models.task import Task  # noqa: E402
from main import app  # noqa: E402

# Страницы-списки и разделы целиком.
PAGES = [
    "/tutor/",
    "/tutor/students",
    "/tutor/students/list",
    "/tutor/students/new",
    "/tutor/groups",
    "/tutor/groups/list",
    "/tutor/groups/new",
    "/tutor/lessons",
    "/tutor/lessons/list",
    "/tutor/calendar",
    "/tutor/unavailability",
    "/tutor/finance",
    "/tutor/finance/operations",
    "/tutor/finance/summary",
    "/tutor/tasks",
    "/tutor/tasks/list",
    "/tutor/stats",
    "/tutor/stats/students.csv",
    "/tutor/mailings/templates/new",
    "/tutor/profile",
    "/tutor/settings",
]

# Вкладки финансов: сводка, платежи, должники, аналитика, прогноз.
FINANCE_TABS = ("operations", "payments", "debtors", "analytics", "forecast")

def _detail_pages() -> list[str]:
    """Карточки всех учеников, групп и задач из текущей базы."""
    with SessionLocal() as db:
        students = list(db.scalars(select(Student.id)).all())
        groups = list(db.scalars(select(Group.id)).all())
        tasks = list(db.scalars(select(Task.id)).all())

    pages = [f"/tutor/students/{sid}" for sid in students]
    pages += [f"/tutor/students/{sid}/finance/summary" for sid in students]
    pages += [f"/tutor/students/{sid}/payments/panel" for sid in students]
    pages += [f"/tutor/students/{sid}/edit" for sid in students]
    pages += [f"/tutor/groups/{gid}/payments" for gid in groups]
    pages += [f"/tutor/groups/{gid}/edit" for gid in groups]
    pages += [f"/tutor/tasks/{tid}/edit" for tid in tasks]
    pages += [f"/tutor/finance/tabs/{tab}" for tab in FINANCE_TABS]
    return pages

def main() -> None:
    """Входит демо-репетитором и обходит все страницы, считая ошибки."""
    failures = 0
    with TestClient(app) as client:
        login = client.post(
            "/tutor/login",
            data={"email": "demo@example.com", "password": "12345678"},
            follow_redirects=False,
        )
        print("login:", login.status_code)
        if login.status_code != 303:
            raise SystemExit(login.text[:1000])

        for page in PAGES + _detail_pages():
            response = client.get(page)
            body = response.text
            marker = ""
            if response.status_code != 200:
                marker = "  <-- FAIL"
                failures += 1
            elif "Internal Server Error" in body or "Traceback (most recent call last)" in body:
                marker = "  <-- ERROR IN BODY"
                failures += 1
            print(f"{response.status_code}  {len(body):>7} B  {page}{marker}")

    print()
    print("Ошибок:", failures)
    if failures:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
