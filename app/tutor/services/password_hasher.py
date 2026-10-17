"""Хеширование паролей: PBKDF2-HMAC-SHA256 на стандартной библиотеке.

Формат хранения: `pbkdf2_sha256$<итерации>$<соль_hex>$<хеш_hex>`.

Префикс и итерации хранятся рядом с хешем, поэтому алгоритм можно
сменить без ломки данных: старые хеши остаются верифицируемыми.
"""

import hashlib
import hmac
import secrets

# Алгоритм и стоимость (OWASP рекомендует ~600 000 для PBKDF2-SHA256).
ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
SALT_BYTES = 16


class PasswordHasher:
    """Хеширует пароли и проверяет их; формат — см. модуль."""

    def hash(self, password: str) -> str:
        """Возвращает строку вида `pbkdf2_sha256$итерации$соль$хеш`."""
        salt = secrets.token_bytes(SALT_BYTES)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, ITERATIONS
        )
        return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, stored: str | None) -> bool:
        """True, если `password` соответствует сохранённому хешу `stored`."""
        if not stored:
            return False
        parts = stored.split("$")
        if len(parts) != 4:
            return False
        algorithm, iterations, salt_hex, digest_hex = parts
        if algorithm != ALGORITHM:
            return False
        try:
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            iterations_n = int(iterations)
        except ValueError:
            return False
        if iterations_n <= 0:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations_n
        )
        return hmac.compare_digest(candidate, expected)
