from __future__ import annotations

import base64
import html
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .attachment_extraction import (
    docx_text as _docx_text,
    extract_attachment,
    extract_attachment_text,
)
from .models import AttachmentText, ConversationMessage, InboundEmail


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailClient:
    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token_reader.json",
    ) -> None:
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.service = self._build_service()
        self._thread_cache: dict[str, list[ConversationMessage]] = {}

    def fetch_messages(self, query: str, limit: int) -> list[InboundEmail]:
        messages = self._list_message_ids(query=query, limit=limit)
        return [self.fetch_message(message_id) for message_id in messages]

    def fetch_message(self, message_id: str) -> InboundEmail:
        message = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = message.get("payload", {})
        headers = _headers(payload)
        body_text, variant = _extract_body(payload)
        attachments = self._extract_attachments(message_id, payload)
        conversation_messages = self._conversation_messages(message.get("threadId"))
        return InboundEmail(
            email_id=message.get("id", message_id),
            conv_id=_conversation_id(message.get("threadId")),
            from_email=_first_address(headers.get("from")),
            to_email=_first_address(headers.get("to")),
            subject=headers.get("subject"),
            body_text=body_text,
            emailbody_variant=variant,
            received_at=_received_at(message, headers),
            has_attachments=bool(attachments),
            attachments=attachments,
            conversation_messages=conversation_messages,
        )

    def _build_service(self):
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)
            _persist_token(self.token_path, creds.to_json())
        return build("gmail", "v1", credentials=creds)

    def _list_message_ids(self, query: str, limit: int) -> list[str]:
        ids: list[str] = []
        page_token: str | None = None
        while len(ids) < limit:
            response = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=min(100, limit - len(ids)),
                    pageToken=page_token,
                )
                .execute()
            )
            ids.extend(message["id"] for message in response.get("messages", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return ids[:limit]

    def _conversation_messages(self, thread_id: str | None) -> list[ConversationMessage]:
        if not thread_id:
            return []
        if thread_id in self._thread_cache:
            return self._thread_cache[thread_id]

        thread = (
            self.service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
        messages = sorted(thread.get("messages", []) or [], key=_message_timestamp)
        conversation = [
            self._conversation_message_from_gmail_message(message)
            for message in messages
        ]
        self._thread_cache[thread_id] = conversation
        return conversation

    def _conversation_message_from_gmail_message(
        self,
        message: dict[str, Any],
    ) -> ConversationMessage:
        message_id = message.get("id", "")
        payload = message.get("payload", {})
        headers = _headers(payload)
        body_text, variant = _extract_body(payload)
        attachments = self._extract_attachments(message_id, payload)
        return ConversationMessage(
            email_id=message_id,
            from_email=_first_address(headers.get("from")),
            to_email=_first_address(headers.get("to")),
            subject=headers.get("subject"),
            body_text=body_text,
            emailbody_variant=variant,
            received_at=_received_at(message, headers),
            attachments=attachments,
        )

    def _extract_attachments(self, message_id: str, payload: dict[str, Any]) -> list[AttachmentText]:
        attachments: list[AttachmentText] = []
        for part in _walk_parts(payload):
            filename = part.get("filename") or ""
            body = part.get("body", {})
            if not filename or not body:
                continue

            raw_bytes: bytes | None = None
            if body.get("attachmentId"):
                attachment = (
                    self.service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=message_id, id=body["attachmentId"])
                    .execute()
                )
                raw_bytes = _decode_base64(attachment.get("data", ""))
            elif body.get("data"):
                raw_bytes = _decode_base64(body["data"])

            if raw_bytes is None:
                continue
            mime_type = part.get("mimeType")
            extraction = extract_attachment(filename, mime_type, raw_bytes)
            attachments.append(
                AttachmentText(
                    filename=filename,
                    mime_type=mime_type,
                    source=f"attachment:{filename}",
                    text=extraction.text,
                    text_extracted=bool(extraction.text),
                    text_preview=_preview(extraction.text),
                    error=extraction.error,
                    extraction_method=extraction.extraction_method,
                    ocr_used=extraction.ocr_used,
                    ocr_confidence=extraction.ocr_confidence,
                    page_count=extraction.page_count,
                    ocr_page_count=extraction.ocr_page_count,
                    review_required=extraction.review_required,
                    review_reason=extraction.review_reason,
                )
            )
        return attachments


def _extract_body(payload: dict[str, Any]) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in _walk_parts(payload):
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if not data:
            continue
        decoded = _decode_base64(data).decode(_charset(part), errors="replace")
        if mime_type == "text/plain":
            plain_parts.append(decoded.strip())
        elif mime_type == "text/html":
            html_parts.append(_html_to_text(decoded))

    html_body = _join_body_parts(html_parts)
    if html_body:
        return html_body, "html"
    plain_body = _join_body_parts(plain_parts)
    if plain_body:
        return plain_body, "plain"
    return "", "plain"


_extract_attachment_text = extract_attachment_text


def _walk_parts(payload: dict[str, Any]):
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _walk_parts(part)


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    return {
        header.get("name", "").lower(): header.get("value", "")
        for header in payload.get("headers", [])
    }


def _conversation_id(thread_id: str | None) -> str | None:
    if not thread_id:
        return None
    return f"gmail-thread:{thread_id}"


def _received_at(message: dict[str, Any], headers: dict[str, str]) -> str | None:
    if message.get("internalDate"):
        timestamp = int(message["internalDate"]) / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    if headers.get("date"):
        try:
            parsed = parsedate_to_datetime(headers["date"])
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except (TypeError, ValueError):
            return None
    return None


def _message_timestamp(message: dict[str, Any]) -> int:
    try:
        return int(message.get("internalDate") or 0)
    except (TypeError, ValueError):
        return 0


def _first_address(value: str | None) -> str | None:
    if not value:
        return None
    addresses = getaddresses([value])
    return addresses[0][1] if addresses else value


def _decode_base64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _charset(part: dict[str, Any]) -> str:
    content_type = next(
        (
            header.get("value", "")
            for header in part.get("headers", [])
            if header.get("name", "").lower() == "content-type"
        ),
        "",
    )
    match = re.search(r"charset=['\"]?([^;'\"\s]+)", content_type, re.I)
    return match.group(1) if match else "utf-8"


def _html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<(script|style).*?</\1>", " ", value)
    value = re.sub(r"(?is)<head.*?</head>", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</(p|div|section|article|h[1-6]|tr)\s*>", "\n", value)
    value = re.sub(r"(?i)</(td|th)\s*>", " | ", value)
    value = re.sub(r"(?i)<li[^>]*>", "\n- ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s+\|\s+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _join_body_parts(parts: list[str]) -> str:
    return "\n".join(part for part in (part.strip() for part in parts) if part).strip()


def _preview(text: str, limit: int = 500) -> str | None:
    text = " ".join(text.split())
    if not text:
        return None
    return text[:limit]


def _persist_token(path: Path, token_json: str) -> bool:
    try:
        path.write_text(token_json, encoding="utf-8")
        return True
    except OSError:
        if path.exists():
            return False
        raise
