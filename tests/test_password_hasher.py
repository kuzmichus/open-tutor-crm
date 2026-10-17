"""Тесты `PasswordHasher`."""

from app.tutor.services import password_hasher
from app.tutor.services.password_hasher import PasswordHasher


def test_hash_differs_from_plaintext():
    hasher = PasswordHasher()
    stored = hasher.hash("секретный-пароль")
    assert stored != "секретный-пароль"
    assert "секретный-пароль" not in stored


def test_hash_format_is_recognized(monkeypatch):
    # Дешёвые итерации только ради скорости теста.
    monkeypatch.setattr(password_hasher, "ITERATIONS", 1000)
    stored = PasswordHasher().hash("pw")
    algorithm, iterations, salt, digest = stored.split("$")
    assert algorithm == "pbkdf2_sha256"
    assert int(iterations) == 1000
    assert len(bytes.fromhex(salt)) == password_hasher.SALT_BYTES
    assert len(bytes.fromhex(digest)) == 32  # SHA-256


def test_verify_correct_and_wrong_password(monkeypatch):
    monkeypatch.setattr(password_hasher, "ITERATIONS", 1000)
    hasher = PasswordHasher()
    stored = hasher.hash("правильный-пароль")
    assert hasher.verify("правильный-пароль", stored) is True
    assert hasher.verify("неверный-пароль", stored) is False


def test_two_hashes_of_same_password_differ(monkeypatch):
    monkeypatch.setattr(password_hasher, "ITERATIONS", 1000)
    hasher = PasswordHasher()
    assert hasher.hash("один-и-тот-же") != hasher.hash("один-и-тот-же")


def test_verify_rejects_malformed_or_empty_stored():
    hasher = PasswordHasher()
    assert hasher.verify("pw", None) is False
    assert hasher.verify("pw", "") is False
    assert hasher.verify("pw", "не-хеш") is False
    assert hasher.verify("pw", "pbkdf2_sha256$abc$zz$zz") is False
    assert hasher.verify("pw", "другой_алгоритм$1000$aa$bb") is False


def test_default_iterations_are_sensible():
    # Реальная стоимость по умолчанию не урезается.
    assert password_hasher.ITERATIONS >= 100_000
