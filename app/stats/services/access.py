"""Доступ к страницам статистики: ри-экспорт общего доступа.

`require_tutor_id` и `LoginRequired` живут в `app/common/access.py`; здесь они
ри-экспортируются, чтобы вьюхи модуля не зависели от `common` напрямую
(тот же приём, что в `student/services/access.py`). `tutor_id` берётся только
из сессии — никогда из query или формы.
"""

from app.common.access import LOGIN_URL, LoginRequired, require_tutor_id

__all__ = ["LOGIN_URL", "LoginRequired", "require_tutor_id"]
