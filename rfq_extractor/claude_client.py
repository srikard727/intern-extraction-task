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
- Extract one item per distinct glass product, mark, size, or makeup.
- Always return an items list, even for one item.
- Do not guess required values. Use null when a value is missing or ambiguous.
- Dimensions must be raw strings as written, not normalized decimals.
- Attribute every field to "body" or "attachment:<filename>" in field_sources.
- Prefer the latest explicit correction in the email body, but note the correction.
- If body and attachment conflict, include both values in review.conflicts.

Item JSON shape:
{
  "mark": string|null,
  "dimensions": {"width": string|null, "height": string|null, "diameter": string|null, "shape": string|null, "raw": string|null}|null,
  "quantity": integer|string|null,
  "TK": string|null,
  "HT": "tempered"|"heat-strengthened"|"annealed"|string|null,
  "TT": string|null,
  "makeup": "monolithic"|"laminated"|"insulated"|"laminated-insulated"|"unknown",
  "airspace": string|null,
  "overall_thickness": string|null,
  "coating": string|null,
  "edge_work": string|null,
  "interlayer": string|null,
  "lite_makeup": [{"position": string|null, "thickness": string|null, "HT": string|null, "TT": string|null, "interlayer": string|null, "notes": string|null}],
  "source": "body"|"attachment:<filename>",
  "field_sources": {"field_name": "body"|"attachment:<filename>"},
  "notes": string|null
}

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
