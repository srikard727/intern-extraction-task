from __future__ import annotations

import base64
import html
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import pdfplumber
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .models import AttachmentText, InboundEmail


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
        return InboundEmail(
            email_id=message.get("id", message_id),
            conv_id=message.get("threadId"),
            from_email=_first_address(headers.get("from")),
            to_email=_first_address(headers.get("to")),
            subject=headers.get("subject"),
            body_text=body_text,
            emailbody_variant=variant,
            received_at=_received_at(message, headers),
            has_attachments=bool(attachments),
            attachments=attachments,
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
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
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
            text, error = _extract_attachment_text(filename, mime_type, raw_bytes)
            attachments.append(
                AttachmentText(
                    filename=filename,
                    mime_type=mime_type,
                    source=f"attachment:{filename}",
                    text=text,
                    text_extracted=bool(text),
                    text_preview=_preview(text),
                    error=error,
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

    if plain_parts:
        return "\n".join(part for part in plain_parts if part).strip(), "plain"
    if html_parts:
        return "\n".join(part for part in html_parts if part).strip(), "html"
    return "", "plain"


def _extract_attachment_text(
    filename: str,
    mime_type: str | None,
    raw_bytes: bytes,
) -> tuple[str, str | None]:
    lower = filename.lower()
    try:
        if mime_type == "application/pdf" or lower.endswith(".pdf"):
            with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            return text.strip(), None
        if lower.endswith(".docx"):
            return _docx_text(raw_bytes), None
        if (mime_type or "").startswith("text/") or lower.endswith((".txt", ".csv", ".tsv")):
            return raw_bytes.decode("utf-8", errors="replace").strip(), None
        return "", f"Unsupported attachment type: {mime_type or lower}"
    except Exception as exc:  # pragma: no cover - depends on external files
        return "", f"{type(exc).__name__}: {exc}"


def _docx_text(raw_bytes: bytes) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(BytesIO(raw_bytes)) as docx:
        root = ET.fromstring(docx.read("word/document.xml"))
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", ns):
        parts = [node.text for node in para.findall(".//w:t", ns) if node.text]
        if parts:
            paragraphs.append("".join(parts))
    return "\n".join(paragraphs).strip()


def _walk_parts(payload: dict[str, Any]):
    yield payload
    for part in payload.get("parts", []) or []:
        yield from _walk_parts(part)


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    return {
        header.get("name", "").lower(): header.get("value", "")
        for header in payload.get("headers", [])
    }


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
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"[ \t]+", " ", value).strip()


def _preview(text: str, limit: int = 500) -> str | None:
    text = " ".join(text.split())
    if not text:
        return None
    return text[:limit]
