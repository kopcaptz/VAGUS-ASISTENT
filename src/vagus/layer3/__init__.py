"""
Слой 3: Каналы взаимодействия (Telegram, API, и др.).
"""

from .channels.gateway import ChannelGateway

__all__ = [
    "ChannelGateway",
]
