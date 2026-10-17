"""Сборщик роутеров модуля tutor."""

from fastapi import APIRouter

from app.tutor.views import (
    home,
    login,
    logout,
    register,
    remember_password,
    reset_password,
)

router = APIRouter()
router.include_router(home.router)
router.include_router(login.router)
router.include_router(register.router)
router.include_router(logout.router)
router.include_router(remember_password.router)
router.include_router(reset_password.router)
