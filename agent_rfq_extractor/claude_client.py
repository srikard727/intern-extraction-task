from __future__ import annotations

import json
import os
import re
from typing import Any

from anthropic import Anthropic

from .models import InboundEmail


DEFAULT_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You extract glass RFQ specifications for a glass fabricator.

Return strict JSON only. Do not include prose or markdown.

Core rules:
- Extract one item per distinct glass product, mark, size, or glass type.
- Always return an items list, even for one item.
- Do not guess required glass specification values. Use null when a required spec value is missing or ambiguous.
- If quantity is not stated, set quantity to 1 and note that it was defaulted.
- If quantity is defaulted, set field_sources.quantity to "default", not "body".
- Dimensions must be raw strings as written, not normalized decimals.
- Square footage / area totals such as "120 sq. ft." are not dimensions. If only area is given, set dimensions to null and explain in notes.
- Include shape for every item. Use "rectangle" for normal width x height glass, "circle" for round/diameter/radius glass, and "square" when only one side is given or the shape is otherwise unclear.
- Holes, pull holes, cutouts, notches, or drilled circles do not make the glass shape circle. Keep shape rectangle when the glass size is width x height.
- Attribute every field to "body" or "attachment:<filename>" in field_sources.
- Prefer the latest explicit correction in the email body, but note the correction.
- If body and attachment conflict, include both values in review.conflicts.
- Use glass_type-specific fields. Do not include laminated/insulated fields on monolithic items.
- Include null for missing fields that are required for that glass_type. Omit fields that are irrelevant to that glass_type.
- Airspace/spacer thickness must be an explicit measurement like "1/2\"" or "12mm"; words like "standard" are not valid spacer_thickness values and should be null with a note.
- spacer_material is the spacer/bar material such as black spacer, silver spacer, aluminum spacer, stainless spacer, or warm edge spacer. Argon/krypton are gas fills, not spacer_material.
- Overall thickness may be included as context for insulated or laminated-insulated items, but it does not replace the required per-lite fields unless spacer_thickness can be derived from known lites.
- Do not inherit a heat treatment or color from a different item/lite unless the email clearly says it applies. For laminated-insulated glass, an inboard "1/4 HS" does not make the outboard laminated plies HS.

Common item fields:
{
  "mark": string|null,
  "dimensions": {"width": string|null, "height": string|null, "diameter": string|null, "shape": string|null, "raw": string|null}|null,
  "quantity": integer,
  "shape": "rectangle"|"square"|"circle",
  "glass_type": "monolithic"|"laminated"|"insulated"|"laminated-insulated"|"unknown",
  "coating": string|null,
  "edge_work": string|null,
  "source": "body"|"attachment:<filename>",
  "field_sources": {"field_name": "body"|"attachment:<filename>"},
  "notes": string|null
}

Monolithic required/spec fields:
{
  "TK": string|null,
  "HT": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT": string|null
}

Laminated required/spec fields:
{
  "TK1": string|null,
  "HT1": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT1": string|null,
  "TK2": string|null,
  "HT2": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT2": string|null,
  "interlayer_material": string|null,
  "interlayer_thickness": string|null
}

Insulated required/spec fields:
{
  "TK1": string|null,
  "HT1": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT1": string|null,
  "TK2": string|null,
  "HT2": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT2": string|null,
  "spacer_material": string|null,
  "spacer_thickness": string|null,
  "overall_thickness": string|null
}

Laminated-insulated required/spec fields:
{
  "laminate_lite": "outboard"|"inboard"|"lite 1"|"lite 2"|string|null,
  "TK1": string|null,
  "HT1": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT1": string|null,
  "TK2": string|null,
  "HT2": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT2": string|null,
  "interlayer_material": string|null,
  "interlayer_thickness": string|null,
  "spacer_material": string|null,
  "spacer_thickness": string|null,
  "TK3": string|null,
  "HT3": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT3": string|null,
  "overall_thickness": string|null
}

When a construction is written like 1/4" clear HS + .060 PVB + 1/4" clear HS:
- TK1=1/4", HT1=heat-strengthened, TT1=clear
- interlayer_thickness=.060", interlayer_material=PVB
- TK2=1/4", HT2=heat-strengthened, TT2=clear

When a construction is written like 1/4" temp / 1/2" airspace / 1/4" temp:
- TK1=1/4", HT1=tempered
- spacer_thickness=1/2"
- TK2=1/4", HT2=tempered

Email-level JSON shape:
{
  "items": [item],
  "review": {
    "reason": string|null,
    "conflicts": [{"field": string, "body": string|null, "attachment": string|null, "source": string|null}]
  }
}
"""


class ClaudeExtractor:
    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        self.model = model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL
        timeout = float(os.getenv("ANTHROPIC_TIMEOUT_SECONDS", "60"))
        self.client = Anthropic(
            api_key=api_key or os.environ["ANTHROPIC_API_KEY"],
            timeout=timeout,
            max_retries=2,
        )

    def extract(self, email: InboundEmail) -> dict[str, Any]:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=5000,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": self._prompt_for_email(email)}],
        )
        text = _response_text(response)
        parsed = _parse_json(text)
        if not isinstance(parsed, dict):
            raise ValueError("Claude returned a non-object JSON payload")
        parsed.setdefault("items", [])
        parsed.setdefault("review", {"reason": None, "conflicts": []})
        return parsed

    def _prompt_for_email(self, email: InboundEmail) -> str:
        attachment_blocks = []
        for attachment in email.attachments:
            if not attachment.text:
                continue
            attachment_blocks.append(
                f"Source: {attachment.source}\n"
                f"Filename: {attachment.filename}\n"
                f"Text:\n{_clip(attachment.text, 12000)}"
            )
        attachments_text = "\n\n".join(attachment_blocks) or "(none)"
        return f"""Extract the RFQ items from this email.

Metadata:
- email_id: {email.email_id}
- subject: {email.subject or ""}

Source: body
Body:
{_clip(email.body_text, 16000)}

Attachments:
{attachments_text}
"""


def _response_text(response: Any) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fenced:
        return json.loads(fenced.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("Could not parse JSON from Claude response")


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated]"
