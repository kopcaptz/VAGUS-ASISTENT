"""
Роутер аутентификации.
Эндпоинты: логин, logout, refresh токена, регистрация.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth")
