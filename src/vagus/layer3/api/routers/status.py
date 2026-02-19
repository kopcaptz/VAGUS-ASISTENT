"""
Роутер статуса и здоровья системы.
Эндпоинты: health check, метрики, версия API.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/status")
