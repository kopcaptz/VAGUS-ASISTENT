"""
Специализированные агенты (Researcher, Coder, Analyst, Summarizer).
"""

from .base_agent import BaseAgent
from .researcher import ResearcherAgent

__all__ = ["BaseAgent", "ResearcherAgent"]
