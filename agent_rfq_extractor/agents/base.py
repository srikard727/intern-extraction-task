from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, ClassVar, Generic, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field


AgentStatus = Literal["completed", "human_review_required", "extraction_failed", "failed"]
InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class AgentContext(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    parent_run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel, Generic[OutputT]):
    agent_name: str
    status: AgentStatus
    output: OutputT | None = None
    error: str | None = None
    started_at: str
    finished_at: str
    duration_ms: int
    context: AgentContext
    metadata: dict[str, Any] = Field(default_factory=dict)

    def require_output(self) -> OutputT:
        if self.output is None:
            raise RuntimeError(
                f"Agent {self.agent_name} did not produce output: {self.error or 'unknown error'}"
            )
        return self.output


class BaseAgent(ABC, Generic[InputT, OutputT]):
    name: ClassVar[str]
    description: ClassVar[str] = ""

    def run(self, payload: InputT, context: AgentContext | None = None) -> AgentResult[OutputT]:
        context = context or AgentContext()
        started = _now()
        start_counter = perf_counter()
        try:
            output = self.execute(payload, context)
            status = self.status_for_output(output)
            error = None
        except Exception as exc:
            output = None
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
        finished = _now()
        return AgentResult(
            agent_name=self.name,
            status=status,
            output=output,
            error=error,
            started_at=started,
            finished_at=finished,
            duration_ms=round((perf_counter() - start_counter) * 1000),
            context=context,
            metadata=self.result_metadata(output),
        )

    @abstractmethod
    def execute(self, payload: InputT, context: AgentContext) -> OutputT:
        raise NotImplementedError

    def status_for_output(self, output: OutputT) -> AgentStatus:
        status = getattr(output, "status", None)
        if status in {"completed", "human_review_required", "extraction_failed"}:
            return status
        return "completed"

    def result_metadata(self, output: OutputT | None) -> dict[str, Any]:
        return {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
