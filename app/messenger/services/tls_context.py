"""SSL-контекст для вызовов Bot API мессенджеров.

Сертификат `platform-api2.max.ru` подписан корнем Минцифры («Russian
Trusted Root CA»), которого нет в хранилищах большинства систем, и этот
корень — на алгоритме ГОСТ, который OpenSSL в Python не проверяет даже
с установленным сертификатом: «докрутить» хранилище нельзя. Флаг
`MESSENGER_TLS_VERIFY=false` отключает проверку подлинности сервера —
канал остаётся зашифрованным. Отключение — осознанное действие владельца
через окружение, а не молчаливое поведение кода.
"""

import ssl

from app.config import settings


def api_ssl_context() -> ssl.SSLContext:
    """Контекст по умолчанию; при выключенном флаге — без проверки.

    Контекст строится на каждый вызов: настройка читается в момент
    запроса, а не при импорте модуля.
    """
    context = ssl.create_default_context()
    if not settings.messenger_tls_verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context
