from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


GlassType = Literal[
    "monolithic",
    "laminated",
    "insulated",
    "laminated-insulated",
    "unknown",
]
Shape = Literal["rectangle", "square", "circle"]


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
    quantity: int = 1
    shape: Shape = "rectangle"
    TK: str | None = None
    HT: str | None = None
    TT: str | None = None
    glass_type: GlassType = "unknown"
    TK1: str | None = None
    HT1: str | None = None
    TT1: str | None = None
    TK2: str | None = None
    HT2: str | None = None
    TT2: str | None = None
    TK3: str | None = None
    HT3: str | None = None
    TT3: str | None = None
    spacer_material: str | None = None
    spacer_thickness: str | None = None
    interlayer_material: str | None = None
    interlayer_thickness: str | None = None
    laminate_lite: str | None = None
    airspace: str | None = None
    overall_thickness: str | None = None
    coating: str | None = None
    edge_work: str | None = None
    interlayer: str | None = None
    lite_details: list[dict[str, Any]] = Field(default_factory=list)
    source: str = "body"
    field_sources: dict[str, str] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    notes: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        _set_if_present(data, "mark", self.mark)
        data["glass_type"] = self.glass_type
        data["shape"] = self.shape
        data["dimensions"] = self.dimensions.model_dump(mode="json") if self.dimensions else None
        data["quantity"] = self.quantity

        if self.glass_type == "monolithic":
            data["TK"] = self.TK
            data["HT"] = self.HT
            _set_if_present(data, "TT", self.TT)
        elif self.glass_type == "laminated":
            _set_required(data, self, ("TK1", "HT1", "TK2", "HT2"))
            _set_required(data, self, ("interlayer_material", "interlayer_thickness"))
            _set_optional_lite_colors(data, self, 2)
        elif self.glass_type == "insulated":
            _set_required(data, self, ("TK1", "HT1", "TK2", "HT2"))
            _set_required(data, self, ("spacer_material", "spacer_thickness"))
            _set_optional_lite_colors(data, self, 2)
            _set_if_present(data, "overall_thickness", self.overall_thickness)
        elif self.glass_type == "laminated-insulated":
            _set_required(data, self, ("laminate_lite",))
            _set_required(data, self, ("TK1", "HT1", "TK2", "HT2", "TK3", "HT3"))
            _set_required(data, self, ("interlayer_material", "interlayer_thickness"))
            _set_required(data, self, ("spacer_material", "spacer_thickness"))
            _set_optional_lite_colors(data, self, 3)
            _set_if_present(data, "overall_thickness", self.overall_thickness)
        else:
            _set_if_present(data, "TK", self.TK)
            _set_if_present(data, "HT", self.HT)
            _set_if_present(data, "TT", self.TT)

        _set_if_present(data, "coating", self.coating)
        _set_if_present(data, "edge_work", self.edge_work)
        data["source"] = self.source
        if self.field_sources:
            data["field_sources"] = self.field_sources
        data["missing_fields"] = self.missing_fields
        _set_if_present(data, "notes", self.notes)
        return data


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
        data = self.model_dump(mode="json", exclude={"items"})
        data["items"] = [item.to_jsonable() for item in self.items]
        return data


def _set_if_present(data: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value != "":
        data[key] = value


def _set_required(data: dict[str, Any], item: RFQItem, fields: tuple[str, ...]) -> None:
    for field in fields:
        data[field] = getattr(item, field)


def _set_optional_lite_colors(data: dict[str, Any], item: RFQItem, count: int) -> None:
    for index in range(1, count + 1):
        key = f"TT{index}"
        _set_if_present(data, key, getattr(item, key))
