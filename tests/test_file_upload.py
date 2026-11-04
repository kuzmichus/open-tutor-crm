"""Тесты загрузки, скачивания и удаления файлов (спека file-storage).

Сеть не используется: локальный бэкенд пишет в `tmp_path`, S3-клиент —
заглушка (правило CI «тесты не ходят в сеть»).
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.cabinet.services.contact_sessions import create_session as create_contact_session
from app.cabinet.services.sessions import create_session as create_student_session
from app.database import SessionLocal
from app.files.models.homework_file import HomeworkFile
from app.files.models.stored_file import StoredFile
from app.homework.models.homework import Homework
from app.homework.services.homework_writer import get_homework
from app.lesson.models.lesson import Lesson
from app.student.models.student_contact import StudentContact

PASSWORD = "Секретный-Пароль-1"
HTMX = {"HX-Request": "true"}

@pytest.fixture(autouse=True)
def local_files(tmp_path, monkeypatch):
    """Все загрузки теста идут в `tmp_path`, кэш фабрики сброшен."""
    from app.config import settings
    from app.files.services.storage_factory import get_storage

    monkeypatch.setattr(settings, "files_backend", "local")
    monkeypatch.setattr(settings, "files_local_root", str(tmp_path / "files"))
    monkeypatch.setattr(settings, "files_max_size_mb", 20)
    get_storage.cache_clear()
    yield tmp_path / "files"
    get_storage.cache_clear()

@pytest.fixture()
def owner(client, tutor_factory):
    """Репетитор, вошедший в клиент; возвращает его id."""
    tutor_id = tutor_factory(email="files@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "files@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    return tutor_id

@pytest.fixture()
def owner_lesson(owner, student_factory):
    """Индивидуальный урок вошедшего репетитора; возвращает id и ученика."""
    student = student_factory(tutor_id=owner, first_name="Мария")
    with SessionLocal() as db:
        lesson = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(lesson)
        db.commit()
        return str(lesson.id), student

def _hw_form(**extra) -> dict:
    """Валидная форма панели ДЗ без файлов."""
    data = {"assignment": "§ 12, упр. 4", "status": "assigned"}
    data.update(extra)
    return data

def _upload(lesson_id: str, files: list[tuple[str, bytes, str]], **extra):
    """POST панели ДЗ с файлами: список (имя, тело, тип)."""
    return {
        "data": _hw_form(**extra),
        "files": [("files", item) for item in files],
        "headers": HTMX,
    }

def _stored_files() -> list[StoredFile]:
    with SessionLocal() as db:
        return list(db.scalars(select(StoredFile)).all())

def _links() -> list[HomeworkFile]:
    with SessionLocal() as db:
        return list(db.scalars(select(HomeworkFile)).all())

# --------------------------------------------------------------------------
# Загрузка через панель ДЗ
# --------------------------------------------------------------------------

def test_upload_attaches_files_to_homework(owner, client, owner_lesson, local_files):
    """Файлы сохраняются в хранилище и привязываются к ДЗ в порядке выбора."""
    lesson_id, _ = owner_lesson

    response = client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(
            lesson_id,
            [
                ("условие.pdf", b"%PDF-1.7 task", "application/pdf"),
                ("фото.png", b"\x89PNG scan", "image/png"),
            ],
        ),
    )

    assert response.status_code == 200
    files = _stored_files()
    assert [file.original_name for file in files] == ["условие.pdf", "фото.png"]
    assert [file.backend for file in files] == ["local", "local"]
    assert [file.size for file in files] == [len(b"%PDF-1.7 task"), len(b"\x89PNG scan")]
    # Объекты легли в корень хранилища и читаются с диска.
    for file in files:
        assert (local_files / file.storage_key).is_file()
    # Связь с ДЗ и порядок — по номеру прикрепления.
    links = _links()
    assert [link.position for link in links] == [0, 1]
    # Панель показывает файлы со ссылкой на скачивание и размером.
    assert "условие.pdf" in response.text
    assert "фото.png" in response.text
    assert f'href="/files/{files[0].id}"' in response.text

def test_upload_saves_homework_and_files_together(owner, client, owner_lesson):
    """Успешная загрузка сохраняет и запись ДЗ, и файлы."""
    lesson_id, _ = owner_lesson

    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )

    with SessionLocal() as db:
        saved = get_homework(db, lesson_id)
        assert saved is not None
        assert saved.assignment == "§ 12, упр. 4"

def test_upload_rejected_extension_saves_nothing(owner, client, owner_lesson):
    """Запрещённое расширение: ни файла, ни записи ДЗ (первое сохранение)."""
    lesson_id, _ = owner_lesson

    response = client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(
            lesson_id,
            [
                ("ок.pdf", b"ok", "application/pdf"),
                ("virus.exe", b"MZ", "application/octet-stream"),
            ],
        ),
    )

    assert response.status_code == 200
    assert "недопустимый формат" in response.text
    # Набор прикрепляется целиком или не прикрепляется вовсе.
    assert _stored_files() == []
    assert _links() == []
    with SessionLocal() as db:
        assert get_homework(db, lesson_id) is None

def test_upload_rejected_extension_keeps_existing_homework(
    owner, client, owner_lesson
):
    """Ошибка файла не меняет уже сохранённое ДЗ."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        data=_hw_form(assignment="Старое задание"),
        headers=HTMX,
    )

    response = client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(
            lesson_id,
            [("virus.exe", b"MZ", "application/octet-stream")],
            assignment="Новое задание",
        ),
    )

    assert response.status_code == 200
    assert "недопустимый формат" in response.text
    with SessionLocal() as db:
        saved = get_homework(db, lesson_id)
        assert saved.assignment == "Старое задание"

def test_upload_rejects_oversized_file(owner, client, owner_lesson, monkeypatch):
    """Файл больше лимита отклоняется, запись ДЗ не создаётся."""
    from app.config import settings

    monkeypatch.setattr(settings, "files_max_size_mb", 1)
    lesson_id, _ = owner_lesson

    response = client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("big.pdf", b"x" * (2 * 1024 * 1024), "application/pdf")]),
    )

    assert response.status_code == 200
    assert "больше 1 МБ" in response.text
    assert _stored_files() == []
    with SessionLocal() as db:
        assert get_homework(db, lesson_id) is None

def test_resave_without_files_keeps_attached(owner, client, owner_lesson):
    """Повторное сохранение без выбора файлов не теряет прикреплённые."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        data=_hw_form(assignment="Уточнённое задание"),
        headers=HTMX,
    )

    files = _stored_files()
    assert [file.id for file in files] == [file_id]
    assert len(_links()) == 1

def test_upload_foreign_lesson_is_404(
    owner, client, tutor_factory, student_factory
):
    """Чужой урок: файлы не сохраняются, ответ как при отсутствии урока."""
    other = tutor_factory(email="files-foreign@example.com")
    student = student_factory(tutor_id=other)
    with SessionLocal() as db:
        lesson = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(lesson)
        db.commit()
        foreign_id = str(lesson.id)

    response = client.post(
        f"/tutor/lessons/{foreign_id}/homework",
        **_upload(foreign_id, [("a.pdf", b"x", "application/pdf")]),
    )

    assert response.status_code == 404
    assert _stored_files() == []

def test_upload_requires_session(client, tutor_factory, student_factory):
    """Без сессии — редирект на вход, файлы не сохраняются."""
    tutor_id = tutor_factory(email="files-guest@example.com")
    student = student_factory(tutor_id=tutor_id)
    with SessionLocal() as db:
        lesson = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(lesson)
        db.commit()
        lesson_id = str(lesson.id)

    response = client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/tutor/login"
    assert _stored_files() == []

# --------------------------------------------------------------------------
# Скачивание
# --------------------------------------------------------------------------

def _attach_file(lesson_id: str, name="условие.pdf", body=b"%PDF-1.7"):
    """Прикрепляет файл через панель ДЗ; возвращает id файла."""
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as client:
        client.post(
            f"/tutor/lessons/{lesson_id}/homework",
            **_upload(lesson_id, [(name, body, "application/pdf")]),
        )
    return _stored_files()[0].id

def test_owner_downloads_local_file(owner, client, owner_lesson):
    """Владелец получает файл вложением с защитными заголовками."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("условие.pdf", b"%PDF-1.7 task", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    response = client.get(f"/files/{file_id}")

    assert response.status_code == 200
    assert response.content == b"%PDF-1.7 task"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"

def test_other_tutor_gets_404(owner, client, owner_lesson, tutor_factory):
    """Чужой репетитор видит 404 — как будто файла нет."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    client.cookies.clear()
    tutor_factory(email="files-other@example.com", password=PASSWORD)
    client.post(
        "/tutor/login",
        data={"email": "files-other@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert client.get(f"/files/{file_id}").status_code == 404

def test_anonymous_gets_404(client, owner, owner_lesson):
    """Без входа файл недоступен — 404, а не редирект на форму входа."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    client.cookies.clear()
    assert client.get(f"/files/{file_id}").status_code == 404

def test_student_downloads_file_of_own_homework(owner, client, owner_lesson):
    """Ученик скачивает файл задания своего урока."""
    lesson_id, student_id = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"student-body", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    client.cookies.clear()
    with SessionLocal() as db:
        token = create_student_session(db, student_id)
    client.cookies.set("student_session", token)

    response = client.get(f"/files/{file_id}")
    assert response.status_code == 200
    assert response.content == b"student-body"

def test_group_member_downloads_file(owner, client, group_factory, group_member_factory):
    """Участник группы скачивает файл задания группового урока."""
    group_id = group_factory(tutor_id=owner)
    member_id = group_member_factory(group_id=group_id)
    with SessionLocal() as db:
        from app.group.models.group_member import GroupMember

        student_id = db.get(GroupMember, member_id).student_id
        lesson = Lesson(
            group_id=group_id,
            type="group",
            starts_at=datetime(2026, 10, 19, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(lesson)
        db.commit()
        lesson_id = str(lesson.id)

    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"group-body", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    client.cookies.clear()
    with SessionLocal() as db:
        token = create_student_session(db, student_id)
    client.cookies.set("student_session", token)
    assert client.get(f"/files/{file_id}").status_code == 200

def test_stranger_student_gets_404(owner, client, owner_lesson, student_factory):
    """Ученик чужого урока получает 404."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    stranger = student_factory(tutor_id=owner)
    client.cookies.clear()
    with SessionLocal() as db:
        token = create_student_session(db, stranger)
    client.cookies.set("student_session", token)
    assert client.get(f"/files/{file_id}").status_code == 404

def test_parent_downloads_child_file(owner, client, owner_lesson, contact_factory):
    """Родитель привязанного ребёнка скачивает файл задания."""
    lesson_id, student_id = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"parent-body", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    contact_id = contact_factory(tutor_id=owner)
    with SessionLocal() as db:
        db.add(StudentContact(student_id=student_id, contact_id=contact_id))
        db.commit()
        token = create_contact_session(db, contact_id)

    client.cookies.clear()
    client.cookies.set("parent_session", token)
    response = client.get(f"/files/{file_id}")
    assert response.status_code == 200
    assert response.content == b"parent-body"

def test_unlinked_parent_gets_404(owner, client, owner_lesson, contact_factory):
    """Родитель без привязки к ребёнку получает 404."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    contact_id = contact_factory(tutor_id=owner)
    with SessionLocal() as db:
        token = create_contact_session(db, contact_id)
    client.cookies.clear()
    client.cookies.set("parent_session", token)
    assert client.get(f"/files/{file_id}").status_code == 404

def test_missing_object_on_disk_is_404(owner, client, owner_lesson, local_files):
    """Метаданные без объекта на диске — 404, а не 500."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file = _stored_files()[0]
    (local_files / file.storage_key).unlink()

    assert client.get(f"/files/{file.id}").status_code == 404

# --------------------------------------------------------------------------
# S3-бэкенд: редирект на временную ссылку
# --------------------------------------------------------------------------

class FakeS3Client:
    """Заглушка клиента S3: объекты в памяти, ссылка с TTL."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        return {"Body": SimpleNamespace(read=lambda: self.objects[kwargs["Key"]])}

    def delete_object(self, **kwargs):
        self.objects.pop(kwargs["Key"], None)

    def head_object(self, **kwargs):
        if kwargs["Key"] not in self.objects:
            raise RuntimeError("NoSuchKey")
        return {}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://s3.example/{Params['Key']}?ttl={ExpiresIn}"

@pytest.fixture()
def s3_storage(monkeypatch):
    """S3-хранилище с заглушкой клиента вместо сети."""
    from app.files.services.storage_s3 import S3Storage

    client = FakeS3Client()
    storage = S3Storage(
        "bucket",
        prefix="uploads/",
        presign_ttl_seconds=900,
        client_factory=lambda: client,
    )
    monkeypatch.setattr(
        "app.files.services.storage_factory.get_storage", lambda: storage
    )
    monkeypatch.setattr(
        "app.files.views.download.storage_for_backend", lambda backend: storage
    )
    monkeypatch.setattr(
        "app.files.services.removal.storage_for_backend", lambda backend: storage
    )
    return storage, client

def test_s3_upload_writes_to_bucket(owner, client, owner_lesson, s3_storage):
    """Загрузка при S3-бэкенде кладёт объект в бакет с префиксом."""
    storage, s3_client = s3_storage
    lesson_id, _ = owner_lesson

    response = client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"%PDF s3", "application/pdf")]),
    )

    assert response.status_code == 200
    file = _stored_files()[0]
    assert file.backend == "s3"
    assert s3_client.objects[f"uploads/{file.storage_key}"] == b"%PDF s3"

def test_s3_download_redirects_to_presigned_url(owner, client, owner_lesson, s3_storage):
    """Скачивание из S3 — 302 на временную ссылку с TTL из настроек."""
    storage, _ = s3_storage
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file = _stored_files()[0]

    response = client.get(f"/files/{file.id}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://s3.example/uploads/")
    assert "ttl=900" in response.headers["location"]
    assert response.headers["x-content-type-options"] == "nosniff"

# --------------------------------------------------------------------------
# Удаление файла
# --------------------------------------------------------------------------

def test_delete_file_removes_object_and_row(owner, client, owner_lesson, local_files):
    """Удаление убирает объект с диска, строку метаданных и связь с ДЗ."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file = _stored_files()[0]
    path = local_files / file.storage_key
    assert path.is_file()

    response = client.post(
        f"/tutor/lessons/{lesson_id}/homework/files/{file.id}/delete",
        headers=HTMX,
    )

    assert response.status_code == 200
    assert "a.pdf" not in response.text
    assert not path.exists()
    assert _stored_files() == []
    assert _links() == []
    # Запись ДЗ осталась: удаление файла не удаляет задание.
    with SessionLocal() as db:
        assert get_homework(db, lesson_id) is not None

def test_delete_foreign_file_is_404(
    owner, client, owner_lesson, tutor_factory, student_factory
):
    """Файл чужого урока через свой урок удалить нельзя — 404."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    other = tutor_factory(email="files-del@example.com")
    student = student_factory(tutor_id=other)
    with SessionLocal() as db:
        foreign = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 20, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(foreign)
        db.commit()
        foreign_id = str(foreign.id)
        Homework(lesson_id=foreign_id, assignment="Чужое ДЗ")
        db.commit()

    response = client.post(
        f"/tutor/lessons/{foreign_id}/homework/files/{file_id}/delete",
        headers=HTMX,
    )
    assert response.status_code == 404
    assert [file.id for file in _stored_files()] == [file_id]

def test_delete_file_of_other_homework_is_404(owner, client, owner_lesson, student_factory):
    """Файл, привязанный к другому ДЗ, через этот урок не удаляется."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file_id = _stored_files()[0].id

    student = student_factory(tutor_id=owner)
    with SessionLocal() as db:
        second = Lesson(
            student_id=student,
            type="individual",
            starts_at=datetime(2026, 10, 21, 10, 0, tzinfo=UTC),
            duration_min=60,
        )
        db.add(second)
        db.commit()
        second_id = str(second.id)
        db.add(Homework(lesson_id=second_id, assignment="Второе ДЗ"))
        db.commit()

    response = client.post(
        f"/tutor/lessons/{second_id}/homework/files/{file_id}/delete",
        headers=HTMX,
    )
    assert response.status_code == 404
    assert _stored_files() != []

# --------------------------------------------------------------------------
# Удаление урока уносит объекты
# --------------------------------------------------------------------------

def test_delete_lesson_removes_file_objects(owner, client, owner_lesson, local_files):
    """Удаление урока убирает объекты файлов и метаданные."""
    lesson_id, _ = owner_lesson
    client.post(
        f"/tutor/lessons/{lesson_id}/homework",
        **_upload(lesson_id, [("a.pdf", b"x", "application/pdf")]),
    )
    file = _stored_files()[0]
    path = local_files / file.storage_key

    client.post(f"/tutor/lessons/{lesson_id}/delete", headers=HTMX)

    assert not path.exists()
    assert _stored_files() == []
