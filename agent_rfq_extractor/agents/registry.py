from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .base import BaseAgent


AgentFactory = Callable[..., BaseAgent[Any, Any]]


class AgentRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, AgentFactory] = {}

    def register(
        self,
        agent: type[BaseAgent[Any, Any]] | AgentFactory,
        *,
        name: str | None = None,
        replace: bool = False,
    ) -> None:
        agent_name = name or getattr(agent, "name", None)
        if not agent_name:
            raise ValueError("registered agents must define a non-empty name")
        if agent_name in self._factories and not replace:
            raise ValueError(f"agent already registered: {agent_name}")
        self._factories[agent_name] = agent

    def create(self, name: str, **kwargs: Any) -> BaseAgent[Any, Any]:
        try:
            factory = self._factories[name]
        except KeyError as exc:
            available = ", ".join(self.names()) or "(none)"
            raise KeyError(f"unknown agent {name!r}; available agents: {available}") from exc
        return factory(**kwargs)

    def names(self) -> list[str]:
        return sorted(self._factories)

    def has(self, name: str) -> bool:
        return name in self._factories

    def create_workflow(
        self,
        steps: Sequence[str],
        *,
        step_kwargs: Mapping[str, dict[str, Any]] | None = None,
    ) -> "AgentWorkflow":
        from .workflow import AgentWorkflow, AgentWorkflowStep

        kwargs_by_step = step_kwargs or {}
        return AgentWorkflow(
            [
                AgentWorkflowStep(self.create(name, **dict(kwargs_by_step.get(name, {}))))
                for name in steps
            ]
        )


def build_default_registry() -> AgentRegistry:
    from .extractor import ExtractorAgent

    registry = AgentRegistry()
    registry.register(ExtractorAgent)
    return registry
