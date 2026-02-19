"""
Роутер задач.
Эндпоинты: создание, статус, отмена задач. Взаимодействие с оркестратором.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/tasks")
