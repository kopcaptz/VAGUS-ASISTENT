"""Registry for Layer2 agents."""

from __future__ import annotations

from typing import Iterable, Optional

from .agents.base_agent import BaseAgent


class AgentRegistry:
    """Lightweight in-memory registry for specialized agents."""

    def __init__(self, agents: Optional[Iterable[BaseAgent]] = None) -> None:
        self._agents: list[BaseAgent] = []
        if agents:
            for agent in agents:
                self.register(agent)

    def register(self, agent: BaseAgent) -> None:
        """Registers an agent if it is not already present."""
        if agent not in self._agents:
            self._agents.append(agent)

    def list(self) -> list[BaseAgent]:
        """Returns registered agents in insertion order."""
        return list(self._agents)

    def find_by_task_type(self, task_type: str) -> Optional[BaseAgent]:
        """Returns first agent that can handle provided task type."""
        for agent in self._agents:
            if agent.can_handle(task_type):
                return agent
        return self._agents[0] if self._agents else None


__all__ = ["AgentRegistry"]
