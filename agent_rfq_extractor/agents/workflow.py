from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

from .base import AgentContext, AgentResult, AgentStatus, BaseAgent


WorkflowOutputT = TypeVar("WorkflowOutputT")
AgentResultCallback = Callable[[AgentResult[Any]], None]


@dataclass(frozen=True)
class AgentWorkflowStep:
    agent: BaseAgent[Any, Any]
    stop_statuses: tuple[AgentStatus, ...] = ("failed", "extraction_failed")
    output_required: bool = True

    @property
    def agent_name(self) -> str:
        return self.agent.name


class AgentWorkflowResult(BaseModel, Generic[WorkflowOutputT]):
    workflow_id: str
    status: AgentStatus
    output: WorkflowOutputT | None = None
    results: list[AgentResult[Any]] = Field(default_factory=list)
    started_at: str
    finished_at: str
    duration_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def last_result(self) -> AgentResult[Any] | None:
        return self.results[-1] if self.results else None

    def require_output(self) -> WorkflowOutputT:
        if self.output is None:
            error = self.last_result.error if self.last_result else "workflow produced no output"
            raise RuntimeError(f"Agent workflow {self.workflow_id} did not produce output: {error}")
        return self.output


class AgentWorkflow:
    def __init__(self, steps: Sequence[AgentWorkflowStep]) -> None:
        if not steps:
            raise ValueError("agent workflow requires at least one step")
        self.steps = list(steps)

    @property
    def agent_names(self) -> list[str]:
        return [step.agent_name for step in self.steps]

    def agent(self, name: str) -> BaseAgent[Any, Any]:
        for step in self.steps:
            if step.agent_name == name:
                return step.agent
        available = ", ".join(self.agent_names)
        raise KeyError(f"unknown workflow agent {name!r}; available agents: {available}")

    def run(
        self,
        payload: Any,
        *,
        metadata: dict[str, Any] | None = None,
        on_result: AgentResultCallback | None = None,
    ) -> AgentWorkflowResult[Any]:
        workflow_id = str(uuid4())
        started = _now()
        start_counter = perf_counter()
        base_metadata = dict(metadata or {})
        current_payload: Any = payload
        final_output: Any | None = None
        status: AgentStatus = "completed"
        results: list[AgentResult[Any]] = []
        previous_result: AgentResult[Any] | None = None

        for index, step in enumerate(self.steps, start=1):
            context = AgentContext(
                parent_run_id=workflow_id,
                metadata=_step_metadata(
                    base_metadata,
                    workflow_id=workflow_id,
                    step_index=index,
                    step_count=len(self.steps),
                    step_agent=step.agent_name,
                    previous_result=previous_result,
                ),
            )
            result = step.agent.run(current_payload, context=context)
            results.append(result)
            if on_result is not None:
                on_result(result)

            status = result.status
            if result.output is not None:
                current_payload = result.output
                final_output = result.output
            elif step.output_required:
                final_output = None

            if result.status in step.stop_statuses:
                break
            if result.output is None and step.output_required:
                break
            previous_result = result

        finished = _now()
        return AgentWorkflowResult(
            workflow_id=workflow_id,
            status=status,
            output=final_output,
            results=results,
            started_at=started,
            finished_at=finished,
            duration_ms=round((perf_counter() - start_counter) * 1000),
            metadata=base_metadata,
        )


def _step_metadata(
    base_metadata: dict[str, Any],
    *,
    workflow_id: str,
    step_index: int,
    step_count: int,
    step_agent: str,
    previous_result: AgentResult[Any] | None,
) -> dict[str, Any]:
    metadata = dict(base_metadata)
    metadata.update(
        {
            "workflow_id": workflow_id,
            "workflow_step_index": step_index,
            "workflow_step_count": step_count,
            "workflow_step_agent": step_agent,
        }
    )
    if previous_result is not None:
        metadata["previous_agent"] = previous_result.agent_name
        metadata["previous_status"] = previous_result.status
    return metadata


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
