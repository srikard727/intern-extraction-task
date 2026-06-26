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


class ConversationMessage(BaseModel):
    email_id: str
    from_email: str | None = None
    to_email: str | None = None
    subject: str | None = None
    body_text: str = ""
    emailbody_variant: str = "plain"
    received_at: str | None = None
    attachments: list[AttachmentText] = Field(default_factory=list)


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
    conversation_messages: list[ConversationMessage] = Field(default_factory=list)


class RFQItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    mark: str | None = None
    dimensions: Dimensions | None = None
    quantity: int = 1
    shape: Shape = "rectangle"
    TK: str | None = None
    HT: str | None = None
    TT: str | None = None
    color: str | None = None
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
    gas_fill: str | None = None
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
    field_confidence: dict[str, float] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    notes: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return extraction_payload([self])

    def to_glass_unit(self) -> dict[str, Any]:
        unit: dict[str, Any] = {
            "width": self.dimensions.width if self.dimensions else None,
            "height": self.dimensions.height if self.dimensions else None,
            "quantity": self.quantity,
            "unit_of_measurement": self.dimensions.unit if self.dimensions else "inch",
            "shape": self.shape,
            "mark": self.mark,
            "glass_specs": _glass_specs(self),
            "fabrication": _fabrication(self),
            "found_fields": _found_fields(self),
            "missing_fields": _output_missing_fields(self.missing_fields),
            "is_complete": not self.missing_fields,
            "field_confidence": _field_confidence(self),
        }
        if self.glass_type == "monolithic":
            _insert_after(unit, "glass_type", self.glass_type, after="mark")
        _set_if_present(unit, "notes", self.notes)
        return unit


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
        data["extraction"] = extraction_payload(self.items)
        return data


def extraction_payload(items: list[RFQItem]) -> dict[str, Any]:
    groups = group_glass_items(items)
    glass_types = [group["glass_type"] for group in groups]
    return {
        "glass_type": _overall_glass_type(glass_types),
        "glass_types": glass_types,
        "is_complete": bool(groups) and all(group["is_complete"] for group in groups),
        "missing_fields": _dedupe(
            output_field
            for group in groups
            for unit in group["glass_units"]
            for output_field in unit["missing_fields"]
        ),
        "glass_type_groups": groups,
    }


def group_glass_items(items: list[RFQItem]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for glass_type in ("monolithic", "laminated", "insulated", "laminated-insulated", "unknown"):
        typed_items = [item for item in items if item.glass_type == glass_type]
        if typed_items:
            groups.append(glass_type_group(glass_type, typed_items))
    return groups


def glass_type_group(glass_type: str, items: list[RFQItem]) -> dict[str, Any]:
    return {
        "glass_type": glass_type,
        "is_complete": all(not item.missing_fields for item in items),
        "glass_units": [item.to_glass_unit() for item in items],
    }


def _glass_specs(item: RFQItem) -> dict[str, Any]:
    if item.glass_type == "monolithic":
        specs = {
            "TK": item.TK,
            "HT": item.HT,
        }
        _set_if_present(specs, "TT", _monolithic_tt(item))
        _set_if_present(specs, "color", _monolithic_color(item))
        return specs

    if item.glass_type == "laminated":
        specs = {
            "TK1": item.TK1,
            "HT1": item.HT1,
            "TK2": item.TK2,
            "HT2": item.HT2,
            "interlayer_material": item.interlayer_material,
            "interlayer_thickness": item.interlayer_thickness,
        }
        _set_lite_types(specs, item, 2)
        return specs

    if item.glass_type == "insulated":
        specs = {
            "TK1": item.TK1,
            "HT1": item.HT1,
            "TK2": item.TK2,
            "HT2": item.HT2,
            "spacer_thickness": item.spacer_thickness,
            "spacer_material": item.spacer_material,
        }
        _set_lite_types(specs, item, 2)
        _insert_after(specs, "gas_fill", item.gas_fill, after="spacer_thickness")
        return specs

    if item.glass_type == "laminated-insulated":
        specs = {
            "TK1": item.TK1,
            "HT1": item.HT1,
            "TK2": item.TK2,
            "HT2": item.HT2,
            "TK3": item.TK3,
            "HT3": item.HT3,
            "spacer_thickness": item.spacer_thickness,
            "spacer_material": item.spacer_material,
            "interlayer_material": item.interlayer_material,
            "interlayer_thickness": item.interlayer_thickness,
            "laminated_lite": _laminated_lite_output(item.laminate_lite),
        }
        _set_lite_types(specs, item, 3)
        _insert_after(specs, "gas_fill", item.gas_fill, after="spacer_thickness")
        return specs

    specs: dict[str, Any] = {}
    _set_if_present(specs, "TK", item.TK)
    _set_if_present(specs, "HT", item.HT)
    _set_if_present(specs, "TT", item.TT)
    _set_if_present(specs, "color", item.color)
    return specs


def _fabrication(item: RFQItem) -> dict[str, Any]:
    fabrication: dict[str, Any] = {}
    _set_if_present(fabrication, "coatings", item.coating)
    _set_if_present(fabrication, "edge_work", item.edge_work)
    return fabrication


def _required_field_order(item: RFQItem) -> tuple[str, ...]:
    if item.glass_type == "monolithic":
        return ("TK", "HT", "dimensions")
    if item.glass_type == "laminated":
        return (
            "TK1",
            "TK2",
            "interlayer_thickness",
            "interlayer_material",
            "HT1",
            "HT2",
            "dimensions",
        )
    if item.glass_type == "insulated":
        return (
            "TK1",
            "TK2",
            "spacer_material",
            "spacer_thickness",
            "HT1",
            "HT2",
            "dimensions",
        )
    if item.glass_type == "laminated-insulated":
        return (
            "TK1",
            "TK2",
            "TK3",
            "HT1",
            "HT2",
            "HT3",
            "interlayer_material",
            "interlayer_thickness",
            "spacer_material",
            "spacer_thickness",
            "laminate_lite",
            "dimensions",
        )
    return ("glass_type", "dimensions")


def _found_fields(item: RFQItem) -> list[str]:
    if item.glass_type == "monolithic":
        return _present_fields(item, ("TK", "HT", "dimensions"))
    if item.glass_type == "laminated":
        return _present_fields(
            item,
            ("TK1", "TK2", "interlayer_material", "interlayer_thickness", "dimensions"),
        )
    if item.glass_type == "insulated":
        found: list[str] = []
        if item.TK1 and item.TK2:
            found.append("TK")
        if item.spacer_thickness:
            found.append("airspace")
        if item.dimensions is not None:
            found.append("dimensions")
        return found
    if item.glass_type == "laminated-insulated":
        return _present_fields(
            item,
            (
                "TK1",
                "TK2",
                "TK3",
                "spacer_thickness",
                "interlayer_material",
                "interlayer_thickness",
                "laminated_lite",
                "dimensions",
            ),
        )
    return _present_fields(item, ("glass_type", "dimensions"))


def _field_confidence(item: RFQItem) -> dict[str, float]:
    explicit = {
        field: value
        for field, value in item.field_confidence.items()
        if not isinstance(value, bool) and isinstance(value, (int, float)) and 0 <= value <= 1
    }
    return explicit or _heuristic_field_confidence(item)


def _present_fields(item: RFQItem, fields: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for field in fields:
        if field == "dimensions":
            if item.dimensions is not None:
                found.append(field)
        elif field == "glass_type":
            if item.glass_type != "unknown":
                found.append(field)
        elif field == "laminated_lite":
            if item.laminate_lite:
                found.append(field)
        elif getattr(item, field, None):
            found.append(field)
    return found


def _output_missing_fields(fields: list[str]) -> list[str]:
    return ["laminated_lite" if field == "laminate_lite" else field for field in fields]


def _monolithic_tt(item: RFQItem) -> str | None:
    if item.TT and not _is_clear_value(item.TT):
        return item.TT
    if _is_glass_type_value(item.color):
        return item.color
    text = " ".join(part for part in (item.coating, item.mark, item.notes) if part)
    if "spandrel" in text.lower():
        return "spandrel"
    return None


def _monolithic_color(item: RFQItem) -> str | None:
    if item.color and not _is_clear_value(item.color) and not _is_glass_type_value(item.color):
        return item.color
    return _extract_color(item.coating) or _extract_color(item.TT) or _extract_color(item.mark)


def _is_clear_value(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"clear", "clear glass"})


def _is_glass_type_value(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"low-iron", "low iron"})


def _extract_color(value: str | None) -> str | None:
    if not value:
        return None
    text = value.lower()
    for color in (
        "warm grey",
        "warm gray",
        "grey",
        "gray",
        "bronze",
        "white",
        "black",
        "blue",
        "green",
    ):
        if color in text:
            return color
    return None


def _set_if_present(data: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value != "":
        data[key] = value


def _set_lite_types(data: dict[str, Any], item: RFQItem, count: int) -> None:
    for index in range(1, count + 1):
        key = f"TT{index}"
        value = getattr(item, key)
        _insert_after(data, key, value, after=f"TK{index}")


def _insert_after(data: dict[str, Any], key: str, value: Any, after: str) -> None:
    if value is None or value == "" or key in data:
        return
    rebuilt: dict[str, Any] = {}
    inserted = False
    for existing_key, existing_value in data.items():
        rebuilt[existing_key] = existing_value
        if existing_key == after:
            rebuilt[key] = value
            inserted = True
    if not inserted:
        rebuilt[key] = value
    data.clear()
    data.update(rebuilt)


def _overall_glass_type(glass_types: list[str]) -> str:
    if not glass_types:
        return "unknown"
    if len(glass_types) == 1:
        return glass_types[0]
    return "mixed"


def _dedupe(values) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _heuristic_field_confidence(item: RFQItem) -> dict[str, float]:
    scores = _confidence_scores(item.glass_type)
    specs = _glass_specs(item)
    return {field: score for field, score in scores.items() if specs.get(field)}


def _confidence_scores(glass_type: str) -> dict[str, float]:
    if glass_type == "monolithic":
        return {
            "TK": 0.97,
            "HT": 0.97,
            "TT": 0.97,
            "color": 0.97,
        }
    if glass_type == "insulated":
        return {
            "TK1": 0.96,
            "TT1": 0.94,
            "HT1": 0.92,
            "TK2": 0.96,
            "TT2": 0.94,
            "HT2": 0.92,
            "spacer_thickness": 0.95,
            "gas_fill": 0.90,
            "spacer_material": 0.88,
        }
    if glass_type == "laminated-insulated":
        return {
            "TK1": 0.95,
            "TT1": 0.93,
            "HT1": 0.91,
            "TK2": 0.95,
            "TT2": 0.93,
            "HT2": 0.91,
            "TK3": 0.95,
            "TT3": 0.93,
            "HT3": 0.91,
            "spacer_thickness": 0.94,
            "gas_fill": 0.89,
            "spacer_material": 0.87,
            "interlayer_material": 0.95,
            "interlayer_thickness": 0.93,
            "laminated_lite": 0.96,
        }
    return {
        "TK1": 0.97,
        "TT1": 0.95,
        "HT1": 0.93,
        "TK2": 0.97,
        "TT2": 0.95,
        "HT2": 0.93,
        "interlayer_material": 0.96,
        "interlayer_thickness": 0.94,
    }


def _laminated_lite_output(value: str | None) -> str | None:
    if not value:
        return None
    lower = value.lower()
    if lower == "outboard":
        return "outer"
    if lower == "inboard":
        return "inner"
    return value
