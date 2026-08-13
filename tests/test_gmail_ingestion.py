import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_rfq_extractor.claude_client import ClaudeExtractor
from agent_rfq_extractor.gmail_client import _conversation_id, _extract_body, _persist_token
from agent_rfq_extractor.graph import RFQExtractionGraph
from agent_rfq_extractor.models import (
    AttachmentText,
    ConversationMessage,
    InboundEmail,
)


class FakeExtractor:
    model = "fake-model"

    def extract(self, email):
        return {
            "items": [],
            "review": {"reason": "No priced item in the current reply.", "conflicts": []},
        }


class GmailIngestionTests(unittest.TestCase):
    def test_visible_html_body_is_preferred_over_plain_alternative(self):
        payload = {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": _encoded("plain fallback")},
                },
                {
                    "mimeType": "text/html",
                    "body": {
                        "data": _encoded(
                            "<html><body><p>Visible RFQ</p><script>hidden()</script></body></html>"
                        )
                    },
                },
            ],
        }

        body, variant = _extract_body(payload)

        self.assertEqual(variant, "html")
        self.assertIn("Visible RFQ", body)
        self.assertNotIn("hidden", body)

    def test_conversation_id_is_distinct_and_labeled(self):
        self.assertEqual(_conversation_id("thread-123"), "gmail-thread:thread-123")
        self.assertNotEqual(_conversation_id("thread-123"), "thread-123")

    def test_prompt_and_record_include_thread_attachments(self):
        attachment = AttachmentText(
            filename="schedule.txt",
            mime_type="text/plain",
            source="attachment:schedule.txt",
            text="GL-1 24 x 36 1/4 clear tempered",
            text_extracted=True,
        )
        email = InboundEmail(
            email_id="reply-002",
            conv_id="gmail-thread:thread-123",
            body_text="Please use the prior schedule.",
            conversation_messages=[
                ConversationMessage(
                    email_id="message-001",
                    body_text="Original RFQ attached.",
                    attachments=[attachment],
                ),
                ConversationMessage(
                    email_id="reply-002",
                    body_text="Please use the prior schedule.",
                ),
            ],
        )

        prompt = ClaudeExtractor.__new__(ClaudeExtractor)._prompt_for_email(email)
        record = RFQExtractionGraph(FakeExtractor()).process_email(email)

        self.assertIn("attachment:schedule.txt", prompt)
        self.assertIn("GL-1 24 x 36", prompt)
        self.assertEqual(len(record.attachments), 1)
        self.assertEqual(record.attachments[0].message_email_id, "message-001")

    def test_existing_read_only_token_can_be_used_without_writeback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "token.json"
            path.write_text("existing", encoding="utf-8")
            with patch.object(Path, "write_text", side_effect=PermissionError("read only")):
                persisted = _persist_token(path, "refreshed")

        self.assertFalse(persisted)


def _encoded(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


if __name__ == "__main__":
    unittest.main()
