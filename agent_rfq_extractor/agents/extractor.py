from __future__ import annotations

from typing import Any

from ..claude_client import ClaudeExtractor
from ..graph import RFQExtractionGraph
from ..models import EmailRecord, InboundEmail
from .base import AgentContext, BaseAgent


class ExtractorAgent(BaseAgent[InboundEmail, EmailRecord]):
    name = "extractor"
    description = "Extracts structured glass RFQ items from one inbound email."

    def __init__(
        self,
        model: str | None = None,
        extractor: ClaudeExtractor | None = None,
        graph: RFQExtractionGraph | Any | None = None,
    ) -> None:
        if graph is not None:
            self.graph = graph
            self.extractor = extractor
            self._model = model or getattr(graph, "model", None)
            return

        self.extractor = extractor or ClaudeExtractor(model=model)
        self.graph = RFQExtractionGraph(self.extractor)
        self._model = self.extractor.model

    @property
    def model(self) -> str | None:
        if self.extractor is not None:
            return self.extractor.model
        return self._model

    def validate_credentials(self) -> None:
        if self.extractor is None:
            raise RuntimeError("ExtractorAgent has no ClaudeExtractor to validate")
        self.extractor.validate_credentials()

    def process_email(self, email: InboundEmail) -> EmailRecord:
        return self.run(email).require_output()

    def execute(self, payload: InboundEmail, context: AgentContext) -> EmailRecord:
        context.metadata.setdefault("email_id", payload.email_id)
        if payload.conv_id:
            context.metadata.setdefault("conv_id", payload.conv_id)
        if self.model:
            context.metadata.setdefault("model", self.model)
        return self.graph.process_email(payload)

    def result_metadata(self, output: EmailRecord | None) -> dict[str, Any]:
        if output is None:
            return {}
        return {
            "email_id": output.email_id,
            "conv_id": output.conv_id,
            "item_count": len(output.items),
            "review_required": output.status == "human_review_required",
            "llm_model": output.llm_model,
        }
