from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MakeupType = Literal[
    "monolithic",
    "laminated",
    "insulated",
    "laminated-insulated",
    "unknown",
]


class Dimensions(BaseModel):
    width: float
    height: float
    unit: str = "inch"


class Conflict(BaseModel):
    field: str
    body: str | None = None
    attachment: str | None = None
    source: str | None = None


class ReviewInfo(BaseModel):
    reason: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)


class AttachmentInfo(BaseModel):
    filename: str
    mime_type: str | None = None
    source: str
    text_extracted: bool = False
    text_preview: str | None = None
    error: str | None = None


class AttachmentText(AttachmentInfo):
    text: str = ""


class InboundEmail(BaseModel):
    email_id: str
    conv_id: str | None = None
    from_email: str | None = None
    to_email: str | None = None
    subject: str | None = None
    body_text: str = ""
    emailbody_variant: str = "plain"
    received_at: str | None = None
    has_attachments: bool = False
    attachments: list[AttachmentText] = Field(default_factory=list)


class RFQItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    mark: str | None = None
    dimensions: Dimensions | None = None
    quantity: int | None = None
    TK: str | None = None
    HT: str | None = None
    TT: str | None = None
    makeup: MakeupType = "unknown"
    airspace: str | None = None
    overall_thickness: str | None = None
    coating: str | None = None
    edge_work: str | None = None
    interlayer: str | None = None
    lite_makeup: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "body"
    field_sources: dict[str, str] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    notes: str | None = None


class EmailRecord(BaseModel):
    email_id: str
    conv_id: str | None = None
    from_email: str | None = None
    to_email: str | None = None
    subject: str | None = None
    body_text: str
    emailbody_variant: str
    received_at: str | None = None
    has_attachments: bool
    extracted_at: str
    status: Literal["completed", "human_review_required", "extraction_failed"]
    items: list[RFQItem] = Field(default_factory=list)
    review: ReviewInfo | None = None
    attachments: list[AttachmentInfo] = Field(default_factory=list)
    llm_model: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
