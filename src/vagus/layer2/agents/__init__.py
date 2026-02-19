"""
Специализированные агенты (Researcher, Coder, Analyst, Summarizer).
"""

from .base_agent import BaseAgent
from .coder import CoderAgent
from .researcher import ResearcherAgent

__all__ = ["BaseAgent", "CoderAgent", "ResearcherAgent"]
