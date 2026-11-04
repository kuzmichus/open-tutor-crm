"""Тесты хранилища файлов: локальный и S3-бэкенды, фабрика и конфигурация.

Сеть не используется: S3-клиент подменяется заглушкой (правило CI «тесты не
ходят в сеть»), локальное хранилище пишет в `tmp_path`.
"""

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.files.services.storage_factory import get_storage, storage_for_backend
from app.files.services.storage_local import LocalStorage
from app.files.services.storage_s3 import S3Storage
from app.files.services.upload import (
    build_key,
    content_type_for,
    extension_of,
    validate_upload,
)

# --------------------------------------------------------------------------
# Локальное хранилище
# --------------------------------------------------------------------------

def test_local_storage_saves_reads_and_deletes(tmp_path):
    """Запись, чтение, существование и удаление объекта."""
    storage = LocalStorage(tmp_path / "files")

    storage.save("t1/abc.pdf", b"%PDF-1.7", "application/pdf")

    assert storage.exists("t1/abc.pdf") is True
    assert storage.open("t1/abc.pdf") == b"%PDF-1.7"
    # Путь отдаётся для FileResponse — объект лежит на диске.
    assert storage.local_path("t1/abc.pdf").read_bytes() == b"%PDF-1.7"

    storage.delete("t1/abc.pdf")
    assert storage.exists("t1/abc.pdf") is False
    # Повторное удаление — не ошибка (строка могла остаться от сбоя).
    storage.delete("t1/abc.pdf")


def test_local_storage_creates_root(tmp_path):
    """Корень создаётся при инициализации: загрузка не падает на первом файле."""
    root = tmp_path / "nested" / "files"
    assert not root.exists()
    LocalStorage(root)
    assert root.is_dir()


@pytest.mark.parametrize(
    "key",
    ["../escape.pdf", "../../etc/passwd", "/etc/passwd", "t1/../../escape.pdf"],
    ids=["parent", "grandparent", "absolute", "nested-parent"],
)
def test_local_storage_rejects_key_outside_root(tmp_path, key):
    """Ключ вне корня — ошибка: имя файла не должно писать куда угодно."""
    storage = LocalStorage(tmp_path / "files")

    with pytest.raises(ValueError):
        storage.save(key, b"x", "text/plain")
    with pytest.raises(ValueError):
        storage.open(key)
    with pytest.raises(ValueError):
        storage.delete(key)


def test_local_storage_has_no_download_url(tmp_path):
    """Локальный файл отдаёт приложение — временной ссылки нет."""
    storage = LocalStorage(tmp_path / "files")
    assert storage.download_url("t1/a.pdf", "a.pdf", "application/pdf") is None
    assert storage.backend == "local"


# --------------------------------------------------------------------------
# S3-хранилище (заглушка клиента)
# --------------------------------------------------------------------------

class FakeS3Client:
    """Заглушка клиента S3: запоминает вызовы и отдаёт предсказуемый URL."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple] = []

    def put_object(self, **kwargs):
        self.calls.append(("put_object", kwargs))
        self.objects[kwargs["Key"]] = kwargs["Body"]

    def get_object(self, **kwargs):
        self.calls.append(("get_object", kwargs))
        return {"Body": SimpleNamespace(read=lambda: self.objects[kwargs["Key"]])}

    def delete_object(self, **kwargs):
        self.calls.append(("delete_object", kwargs))
        self.objects.pop(kwargs["Key"], None)

    def head_object(self, **kwargs):
        self.calls.append(("head_object", kwargs))
        if kwargs["Key"] not in self.objects:
            raise RuntimeError("NoSuchKey")
        return {}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append(("presign", operation, Params, ExpiresIn))
        return f"https://s3.example/{Params['Key']}?ttl={ExpiresIn}"


def _s3_storage(client: FakeS3Client, ttl: int = 900) -> S3Storage:
    return S3Storage(
        "bucket",
        prefix="uploads/",
        presign_ttl_seconds=ttl,
        client_factory=lambda: client,
    )


def test_s3_storage_saves_with_prefix_and_content_type():
    """Объект кладётся с префиксом из настроек и типом содержимого."""
    client = FakeS3Client()
    storage = _s3_storage(client)

    storage.save("t1/abc.pdf", b"%PDF", "application/pdf")

    put = [call for call in client.calls if call[0] == "put_object"][0][1]
    assert put["Bucket"] == "bucket"
    assert put["Key"] == "uploads/t1/abc.pdf"
    assert put["ContentType"] == "application/pdf"
    assert put["Body"] == b"%PDF"


def test_s3_storage_reads_and_deletes():
    """Чтение и удаление идут по тому же ключу с префиксом."""
    client = FakeS3Client()
    storage = _s3_storage(client)
    storage.save("t1/abc.pdf", b"%PDF", "application/pdf")

    assert storage.open("t1/abc.pdf") == b"%PDF"
    assert storage.exists("t1/abc.pdf") is True
    storage.delete("t1/abc.pdf")
    assert storage.exists("t1/abc.pdf") is False


def test_s3_presigned_url_has_ttl_and_attachment():
    """Presigned URL: TTL из настроек, имя вложения и тип содержимого."""
    client = FakeS3Client()
    storage = _s3_storage(client, ttl=600)

    url = storage.download_url("t1/abc.pdf", "Домашка.pdf", "application/pdf")

    assert url is not None
    presign = [call for call in client.calls if call[0] == "presign"][0]
    assert presign[1] == "get_object"
    assert presign[3] == 600
    assert presign[2]["Key"] == "uploads/t1/abc.pdf"
    assert 'attachment; filename="Домашка.pdf"' == (
        presign[2]["ResponseContentDisposition"]
    )
    assert presign[2]["ResponseContentType"] == "application/pdf"
    assert storage.backend == "s3"
    assert storage.local_path("t1/abc.pdf") is None


# --------------------------------------------------------------------------
# Фабрика: выбор бэкенда по env
# --------------------------------------------------------------------------

@pytest.fixture()
def reset_storage_cache():
    """Сбрасывает кэш фабрики до и после теста (env меняется в тесте)."""
    get_storage.cache_clear()
    yield
    get_storage.cache_clear()


def test_factory_picks_local_backend(monkeypatch, tmp_path, reset_storage_cache):
    """`FILES_BACKEND=local` (по умолчанию) — локальное хранилище."""
    from app.config import settings

    monkeypatch.setattr(settings, "files_backend", "local")
    monkeypatch.setattr(settings, "files_local_root", str(tmp_path / "files"))

    storage = get_storage()

    assert isinstance(storage, LocalStorage)
    assert storage.root == (tmp_path / "files").resolve()


def test_factory_picks_s3_backend(monkeypatch, reset_storage_cache):
    """`FILES_BACKEND=s3` — S3-хранилище с параметрами из настроек."""
    from app.config import settings

    monkeypatch.setattr(settings, "files_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "my-bucket")
    monkeypatch.setattr(settings, "s3_prefix", "homework/")
    monkeypatch.setattr(settings, "files_presign_ttl_seconds", 300)

    storage = get_storage()

    assert isinstance(storage, S3Storage)
    assert storage.bucket == "my-bucket"
    assert storage.prefix == "homework/"
    assert storage.presign_ttl_seconds == 300


def test_storage_for_backend_ignores_current_env(monkeypatch, tmp_path):
    """Старый файл читается своим бэкендом, а не текущим значением env."""
    from app.config import settings

    monkeypatch.setattr(settings, "files_backend", "s3")
    monkeypatch.setattr(settings, "files_local_root", str(tmp_path / "files"))

    # Файл сохранён локально, а env уже переключён на S3.
    assert isinstance(storage_for_backend("local"), LocalStorage)
    assert isinstance(storage_for_backend("s3"), S3Storage)


# --------------------------------------------------------------------------
# Конфигурация
# --------------------------------------------------------------------------

def test_settings_defaults_are_local():
    """По умолчанию — локальное хранилище с безопасным набором расширений."""
    settings = Settings(_env_file=None)

    assert settings.files_backend == "local"
    assert settings.files_max_size_mb == 20
    assert settings.files_presign_ttl_seconds == 900
    assert "pdf" in settings.allowed_extensions
    assert "exe" not in settings.allowed_extensions
    assert settings.max_file_bytes == 20 * 1024 * 1024


def test_settings_extensions_are_normalized():
    """Регистр и точка в env не мешают: «.PDF, Docx» → pdf, docx."""
    settings = Settings(
        _env_file=None,
        files_allowed_extensions=".PDF, Docx , jpg",
    )
    assert settings.allowed_extensions == ("pdf", "docx", "jpg")


def test_settings_s3_requires_bucket_and_keys():
    """Неполная конфигурация S3 — ошибка старта с именами параметров."""
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=None, files_backend="s3")
    message = str(exc.value)
    assert "S3_BUCKET" in message
    assert "S3_ACCESS_KEY_ID" in message
    assert "S3_SECRET_ACCESS_KEY" in message


def test_settings_s3_valid_configuration_passes():
    """Бакет и ключи заданы — приложение стартует."""
    settings = Settings(
        _env_file=None,
        files_backend="s3",
        s3_bucket="bucket",
        s3_access_key_id="key",
        s3_secret_access_key="secret",
    )
    assert settings.files_backend == "s3"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("files_max_size_mb", 0),
        ("files_presign_ttl_seconds", 0),
    ],
)
def test_settings_rejects_non_positive_limits(field, value):
    """Нулевой лимит или TTL — ошибка конфигурации, а не «загрузить ничего»."""
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})


# --------------------------------------------------------------------------
# Валидация загрузки и ключ объекта
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("filename", "size", "expected"),
    [
        ("Домашка.pdf", 1024, []),
        ("scan.PNG", 10, []),
        ("virus.exe", 10, ["формат"]),
        ("noext", 10, ["расширение"]),
        ("", 10, ["Выберите файл"]),
    ],
    ids=["ok", "upper-ext", "bad-ext", "no-ext", "empty-name"],
)
def test_validate_upload_filename(filename, size, expected):
    """Расширение из allowlist и непустое имя — обязательны."""
    errors = validate_upload(filename, size)
    if not expected:
        assert errors == []
    else:
        assert any(fragment in errors[0] for fragment in expected), errors


def test_validate_upload_rejects_oversized_file():
    """Файл больше лимита отклоняется с понятным сообщением."""
    errors = validate_upload("big.pdf", 30 * 1024 * 1024)
    assert len(errors) == 1
    assert "20 МБ" in errors[0]


def test_build_key_has_no_user_filename():
    """Ключ объекта — id репетитора и uuid, имя пользователя не попадает."""
    key = build_key("tutor-1", "Домашняя работа Иванова.pdf")

    tutor_part, name_part = key.split("/")
    assert tutor_part == "tutor-1"
    assert name_part.endswith(".pdf")
    assert "Иванова" not in key
    assert name_part[:-4].isalnum()


def test_build_key_without_extension():
    """Файл без расширения не получает точку в конце ключа."""
    key = build_key("tutor-1", "README")
    assert not key.endswith(".")
    assert "/" in key


@pytest.mark.parametrize(
    ("filename", "declared", "expected"),
    [
        ("a.pdf", "application/pdf", "application/pdf"),
        ("a.pdf", None, "application/pdf"),
        ("a.docx", "application/octet-stream", (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        )),
        ("a.unknown", None, "application/octet-stream"),
    ],
    ids=["declared", "missing", "generic", "unknown"],
)
def test_content_type_for(filename, declared, expected):
    """Тип содержимого: по расширению, если браузер прислал общий тип."""
    assert content_type_for(filename, declared) == expected


def test_extension_of_normalizes_case():
    """Расширение приводится к нижнему регистру."""
    assert extension_of("Scan.PDF") == "pdf"
    assert extension_of("noext") == ""
