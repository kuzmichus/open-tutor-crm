"""Сборщик роутеров модуля tutor."""

from fastapi import APIRouter

from app.tutor.views import (
    home,
    login,
    logout,
    profile,
    profile_calendar,
    profile_channels,
    profile_google_callback,
    profile_google_connect,
    profile_google_disconnect,
    profile_notifications,
    profile_save,
    profile_security,
    register,
    remember_password,
    reset_password,
    settings,
    settings_messengers,
)

router = APIRouter()
router.include_router(home.router)
router.include_router(login.router)
router.include_router(logout.router)
router.include_router(profile.router)
router.include_router(profile_save.router)
router.include_router(profile_security.router)
router.include_router(profile_notifications.router)
router.include_router(profile_calendar.router)
router.include_router(profile_channels.router)
# Подключение Google Календаря: свои пути `/tutor/profile/google/...`,
# с маршрутами вкладок не пересекаются (один эндпоинт на файл).
router.include_router(profile_google_connect.router)
router.include_router(profile_google_callback.router)
router.include_router(profile_google_disconnect.router)
router.include_router(settings.router)
router.include_router(settings_messengers.router)
router.include_router(register.router)
router.include_router(remember_password.router)
router.include_router(reset_password.router)
