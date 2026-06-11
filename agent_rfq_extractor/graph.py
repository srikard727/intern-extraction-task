from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import Any, TypedDict

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
    from langgraph.graph import END, StateGraph

from .claude_client import ClaudeExtractor
from .models import AttachmentInfo, EmailRecord, InboundEmail, RFQItem, ReviewInfo
from .quality import build_review, normalize_items


class ExtractionState(TypedDict, total=False):
    email: InboundEmail
    attachment_infos: list[AttachmentInfo]
    raw: dict[str, Any]
    raw_items: list[dict[str, Any]]
    raw_review: dict[str, Any] | None
    items: list[RFQItem]
    review: ReviewInfo | None
    status: str
    record: EmailRecord
    error: str


class RFQExtractionGraph:
    def __init__(self, extractor: ClaudeExtractor) -> None:
        self.extractor = extractor
        self.graph = self._build_graph()

    @property
    def model(self) -> str:
        return self.extractor.model

    def process_email(self, email: InboundEmail) -> EmailRecord:
        result = self.graph.invoke({"email": email})
        record = result.get("record")
        if not isinstance(record, EmailRecord):
            raise RuntimeError("RFQ extraction graph did not produce an EmailRecord")
        return record

    def _build_graph(self):
        workflow = StateGraph(ExtractionState)
        workflow.add_node("prepare", self._prepare_node)
        workflow.add_node("extract", self._extract_node)
        workflow.add_node("normalize", self._normalize_node)
        workflow.add_node("review", self._review_node)
        workflow.add_node("assemble", self._assemble_node)
        workflow.add_node("failure", self._failure_node)

        workflow.set_entry_point("prepare")
        workflow.add_edge("prepare", "extract")
        workflow.add_conditional_edges(
            "extract",
            _route_after_extract,
            {
                "failure": "failure",
                "normalize": "normalize",
            },
        )
        workflow.add_edge("normalize", "review")
        workflow.add_edge("review", "assemble")
        workflow.add_edge("assemble", END)
        workflow.add_edge("failure", END)
        return workflow.compile()

    def _prepare_node(self, state: ExtractionState) -> ExtractionState:
        email = state["email"]
        return {"attachment_infos": [_attachment_info(attachment) for attachment in email.attachments]}

    def _extract_node(self, state: ExtractionState) -> ExtractionState:
        try:
            raw = self.extractor.extract(state["email"])
            return {"raw": raw}
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    def _normalize_node(self, state: ExtractionState) -> ExtractionState:
        raw = state.get("raw") or {}
        raw_items = raw.get("items") if isinstance(raw.get("items"), list) else []
        raw_review = raw.get("review") if isinstance(raw.get("review"), dict) else None
        return {
            "raw_items": raw_items,
            "raw_review": raw_review,
            "items": normalize_items(raw_items),
        }

    def _review_node(self, state: ExtractionState) -> ExtractionState:
        items = state.get("items", [])
        review = build_review(items, state.get("raw_review"))
        return {
            "review": review,
            "status": "human_review_required" if review else "completed",
        }

    def _assemble_node(self, state: ExtractionState) -> ExtractionState:
        email = state["email"]
        record = EmailRecord(
            **_email_base(email, state.get("attachment_infos", [])),
            extracted_at=_now(),
            status=state.get("status", "completed"),
            items=state.get("items", []),
            review=state.get("review"),
            llm_model=self.model,
        )
        return {"record": record}

    def _failure_node(self, state: ExtractionState) -> ExtractionState:
        email = state["email"]
        error = state.get("error") or "unknown error"
        record = EmailRecord(
            **_email_base(email, state.get("attachment_infos", [])),
            extracted_at=_now(),
            status="extraction_failed",
            items=[],
            review=ReviewInfo(
                reason=f"Extraction failed: {error}",
                missing_fields=[],
                conflicts=[],
            ),
            llm_model=self.model,
        )
        return {"record": record}


def _route_after_extract(state: ExtractionState) -> str:
    return "failure" if state.get("error") else "normalize"


def _email_base(email: InboundEmail, attachments: list[AttachmentInfo]) -> dict[str, Any]:
    return {
        "email_id": email.email_id,
        "conv_id": email.conv_id,
        "from_email": email.from_email,
        "to_email": email.to_email,
        "subject": email.subject,
        "body_text": email.body_text,
        "emailbody_variant": email.emailbody_variant,
        "received_at": email.received_at,
        "has_attachments": email.has_attachments,
        "attachments": attachments,
    }


def _attachment_info(attachment) -> AttachmentInfo:
    data = attachment.model_dump(exclude={"text"})
    return AttachmentInfo(**data)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
