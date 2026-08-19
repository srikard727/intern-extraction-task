from __future__ import annotations

import os
import re
from mimetypes import guess_type
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from .agents import AgentWorkflow, AgentWorkflowStep, ExtractorAgent, build_default_registry
from .attachment_extraction import extract_attachment
from .gmail_client import GmailClient
from .models import AttachmentText, EmailRecord, InboundEmail
from database.factory import create_store, storage_label


class RFQPipeline:
    def __init__(
        self,
        db_path: str | Path,
        json_path: str | Path,
        model: str | None = None,
        replace_existing: bool = False,
        database_url: str | None = None,
    ) -> None:
        load_dotenv(override=False)
        self.db_path = Path(db_path)
        self.json_path = Path(json_path)
        self.database_url = database_url
        self.database_label = storage_label(self.db_path, self.database_url)
        self.agent_registry = build_default_registry()
        extractor_agent = self.agent_registry.create("extractor", model=model)
        if not isinstance(extractor_agent, ExtractorAgent):
            raise TypeError("default registry returned a non-extractor agent for 'extractor'")
        self.extractor_agent = extractor_agent
        self.agent_workflow = AgentWorkflow([AgentWorkflowStep(self.extractor_agent)])
        self.store = create_store(self.db_path, database_url=self.database_url)
        self.replace_existing = replace_existing
        self._run_prepared = False

    @property
    def model(self) -> str:
        return self.extractor_agent.model or ""

    def close(self) -> None:
        self.store.close()

    def validate_llm(self) -> None:
        self.extractor_agent.validate_credentials()

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
        if limit is not None:
            if limit < 1:
                raise ValueError("fixture limit must be at least 1")
            emails = emails[:limit]
        return self.run_emails(emails)

    def run_emails(self, emails: Iterable[InboundEmail]) -> list[EmailRecord]:
        self._prepare_run()
        records: list[EmailRecord] = []
        for index, email in enumerate(emails, start=1):
            print(f"[{index}] extracting {email.email_id}: {email.subject or '(no subject)'}", flush=True)
            record = self.process_email(email)
            self.store.upsert_record(record)
            records.append(record)
            print(f"    -> {record.status} / {len(record.items)} item(s)", flush=True)
        self.store.export_json(self.json_path)
        return records

    def _prepare_run(self) -> None:
        if self._run_prepared:
            return
        if self.replace_existing:
            self.store.clear()
        self._run_prepared = True

    def process_email(self, email: InboundEmail) -> EmailRecord:
        result = self.agent_workflow.run(
            email,
            metadata=_email_workflow_metadata(email, self.model),
            on_result=self.store.record_agent_run,
        )
        return result.require_output()


def parse_fixture(path: str | Path) -> list[InboundEmail]:
    fixture_path = Path(path)
    text = fixture_path.read_text(encoding="utf-8")
    parts = re.split(r"Email:\s*(\d+)", text)
    emails: list[InboundEmail] = []
    for i in range(1, len(parts), 2):
        number = int(parts[i])
        body = _strip_fixture_body(parts[i + 1])
        if not body:
            continue
        body, attachments = _fixture_attachments(body, fixture_path.parent)
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
                has_attachments=bool(attachments),
                attachments=attachments,
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


def _fixture_attachments(
    body: str,
    fixture_directory: Path,
) -> tuple[str, list[AttachmentText]]:
    attachments: list[AttachmentText] = []
    body_lines: list[str] = []
    fixture_root = fixture_directory.resolve()

    for line in body.splitlines():
        match = re.fullmatch(r"\s*Fixture-Attachment:\s*(.+?)\s*", line)
        if not match:
            body_lines.append(line)
            continue

        relative_path = Path(match.group(1))
        if relative_path.is_absolute():
            raise ValueError("fixture attachment paths must be relative to the fixture file")
        attachment_path = (fixture_root / relative_path).resolve()
        if not attachment_path.is_relative_to(fixture_root):
            raise ValueError("fixture attachment path must stay inside the fixture directory")

        filename = attachment_path.name
        mime_type = guess_type(filename)[0]
        if attachment_path.exists():
            extraction = extract_attachment(
                filename,
                mime_type,
                attachment_path.read_bytes(),
            )
        else:
            extraction = None
        text = extraction.text if extraction else ""
        error = extraction.error if extraction else f"Fixture attachment not found: {relative_path}"
        attachments.append(
            AttachmentText(
                filename=filename,
                mime_type=mime_type,
                source=f"attachment:{filename}",
                text=text,
                text_extracted=bool(text),
                text_preview=" ".join(text.split())[:500] or None,
                error=error,
                extraction_method=extraction.extraction_method if extraction else None,
                ocr_used=extraction.ocr_used if extraction else False,
                ocr_confidence=extraction.ocr_confidence if extraction else None,
                page_count=extraction.page_count if extraction else None,
                ocr_page_count=extraction.ocr_page_count if extraction else 0,
                review_required=extraction.review_required if extraction else True,
                review_reason=(
                    extraction.review_reason
                    if extraction
                    else "The fixture attachment is missing and requires manual review."
                ),
            )
        )

    return "\n".join(body_lines).strip(), attachments


def _subject_from_body(body: str) -> str:
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    if any(ch.isdigit() for ch in first) or "glass" in first.lower():
        return "RFQ: " + first[:70]
    return "Request for Quote"


def _email_workflow_metadata(email: InboundEmail, model: str) -> dict[str, str]:
    metadata = {"email_id": email.email_id}
    if email.conv_id:
        metadata["conv_id"] = email.conv_id
    if model:
        metadata["model"] = model
    return metadata
