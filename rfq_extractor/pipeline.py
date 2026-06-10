from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from .claude_client import ClaudeExtractor
from .gmail_client import GmailClient
from .models import AttachmentInfo, EmailRecord, InboundEmail, ReviewInfo
from .quality import build_review, normalize_items
from .storage import ExtractionStore


class RFQPipeline:
    def __init__(
        self,
        db_path: str | Path,
        json_path: str | Path,
        model: str | None = None,
        replace_existing: bool = False,
    ) -> None:
        load_dotenv()
        self.db_path = Path(db_path)
        self.json_path = Path(json_path)
        self.extractor = ClaudeExtractor(model=model)
        self.store = ExtractionStore(self.db_path)
        if replace_existing:
            self.store.clear()

    @property
    def model(self) -> str:
        return self.extractor.model

    def close(self) -> None:
        self.store.close()

    def run_gmail(
        self,
        query: str,
        limit: int,
        credentials_path: str | None = None,
        token_path: str | None = None,
    ) -> list[EmailRecord]:
        client = GmailClient(
            credentials_path=credentials_path or os.getenv("GMAIL_CREDENTIALS", "credentials.json"),
            token_path=token_path or os.getenv("GMAIL_TOKEN", "token_reader.json"),
        )
        emails = client.fetch_messages(query=query, limit=limit)
        return self.run_emails(emails)

    def run_fixture(self, path: str | Path, limit: int | None = None) -> list[EmailRecord]:
        emails = parse_fixture(path)
        if limit:
            emails = emails[:limit]
        return self.run_emails(emails)

    def run_emails(self, emails: Iterable[InboundEmail]) -> list[EmailRecord]:
        records: list[EmailRecord] = []
        for index, email in enumerate(emails, start=1):
            print(f"[{index}] extracting {email.email_id}: {email.subject or '(no subject)'}", flush=True)
            record = self.process_email(email)
            self.store.upsert_record(record)
            records.append(record)
            print(f"    -> {record.status} / {len(record.items)} item(s)", flush=True)
        self.store.export_json(self.json_path)
        return records

    def process_email(self, email: InboundEmail) -> EmailRecord:
        attachment_infos = [_attachment_info(attachment) for attachment in email.attachments]
        try:
            raw = self.extractor.extract(email)
            raw_items = raw.get("items") if isinstance(raw.get("items"), list) else []
            items = normalize_items(raw_items)
            raw_review = raw.get("review") if isinstance(raw.get("review"), dict) else None
            review = build_review(items, raw_review)
            status = "human_review_required" if review else "completed"
            return EmailRecord(
                **_email_base(email, attachment_infos),
                extracted_at=_now(),
                status=status,
                items=items,
                review=review,
                llm_model=self.model,
            )
        except Exception as exc:
            return EmailRecord(
                **_email_base(email, attachment_infos),
                extracted_at=_now(),
                status="extraction_failed",
                items=[],
                review=ReviewInfo(
                    reason=f"Extraction failed: {type(exc).__name__}: {exc}",
                    missing_fields=[],
                    conflicts=[],
                ),
                llm_model=self.model,
            )


def parse_fixture(path: str | Path) -> list[InboundEmail]:
    text = Path(path).read_text(encoding="utf-8")
    parts = re.split(r"Email:\s*(\d+)", text)
    emails: list[InboundEmail] = []
    for i in range(1, len(parts), 2):
        number = int(parts[i])
        body = _strip_fixture_body(parts[i + 1])
        if not body:
            continue
        subject = _subject_from_body(body)
        emails.append(
            InboundEmail(
                email_id=f"fixture-{number:03d}",
                conv_id=f"fixture-{number:03d}",
                from_email="fixture@example.com",
                to_email="fixture@example.com",
                subject=subject,
                body_text=body,
                emailbody_variant="plain",
                received_at=None,
                has_attachments=False,
                attachments=[],
            )
        )
    return emails


def _email_base(email: InboundEmail, attachments: list[AttachmentInfo]) -> dict:
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


def _strip_fixture_body(value: str) -> str:
    lines = []
    for line in value.splitlines():
        if set(line.strip()) == {"-"}:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _subject_from_body(body: str) -> str:
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if any(ch.isdigit() for ch in first) or "glass" in first.lower():
        return "RFQ: " + first[:70]
    return "Request for Quote"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
