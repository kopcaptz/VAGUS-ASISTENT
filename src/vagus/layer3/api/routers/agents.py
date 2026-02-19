"""
Роутер агентов.
Эндпоинты: список агентов, конфигурация, запуск/остановка агентов.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/agents")
