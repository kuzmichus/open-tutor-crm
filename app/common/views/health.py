"""Health-check эндпоинт."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Простой health-check для мониторинга."""
    return {"status": "ok"}
