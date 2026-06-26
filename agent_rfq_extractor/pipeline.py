from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from .claude_client import ClaudeExtractor
from .gmail_client import GmailClient
from .graph import RFQExtractionGraph
from .models import EmailRecord, InboundEmail
from database.storage import ExtractionStore


class RFQPipeline:
    def __init__(
        self,
        db_path: str | Path,
        json_path: str | Path,
        model: str | None = None,
        replace_existing: bool = False,
    ) -> None:
        load_dotenv(override=True)
        self.db_path = Path(db_path)
        self.json_path = Path(json_path)
        self.extractor = ClaudeExtractor(model=model)
        self.graph = RFQExtractionGraph(self.extractor)
        self.store = ExtractionStore(self.db_path)
        if replace_existing:
            self.store.clear()

    @property
    def model(self) -> str:
        return self.extractor.model

    def close(self) -> None:
        self.store.close()

    def validate_llm(self) -> None:
        self.extractor.validate_credentials()

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

    def run_gmail_ids(
        self,
        message_ids: list[str],
        credentials_path: str | None = None,
        token_path: str | None = None,
    ) -> list[EmailRecord]:
        client = GmailClient(
            credentials_path=credentials_path or os.getenv("GMAIL_CREDENTIALS", "credentials.json"),
            token_path=token_path or os.getenv("GMAIL_TOKEN", "token_reader.json"),
        )
        emails = [client.fetch_message(message_id) for message_id in message_ids]
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
        return self.graph.process_email(email)


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
                conv_id=f"fixture-thread-{number:03d}",
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
