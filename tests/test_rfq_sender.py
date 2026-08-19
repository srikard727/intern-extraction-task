import base64
import unittest
from email import message_from_bytes
from email import policy
from types import SimpleNamespace

from rfq_sender import parse_emails, send_one


class RFQSenderTests(unittest.TestCase):
    def test_image_pdf_fixture_emails_include_local_attachments(self):
        emails = parse_emails("fixtures/image_pdf_rfq_emails.txt")

        self.assertEqual(len(emails), 3)
        self.assertEqual(emails[0]["attachments"][0].name, "image_rfq_monolithic.pdf")
        self.assertNotIn("Fixture-Attachment", emails[0]["body"])

    def test_send_one_builds_pdf_mime_attachment(self):
        email = parse_emails("fixtures/image_pdf_rfq_emails.txt")[0]
        captured = {}

        def send(userId, body):
            captured.update(body)
            return SimpleNamespace(execute=lambda: {"id": "message-1", "threadId": "thread-1"})

        messages = SimpleNamespace(send=send)
        users = SimpleNamespace(messages=lambda: messages)
        service = SimpleNamespace(users=lambda: users)

        result = send_one(
            service,
            email["subject"],
            email["body"],
            "sender@example.com",
            attachments=email["attachments"],
        )

        raw = base64.urlsafe_b64decode(captured["raw"] + "===")
        message = message_from_bytes(raw, policy=policy.default)
        attachments = list(message.iter_attachments())
        self.assertEqual(result["email_id"], "message-1")
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "image_rfq_monolithic.pdf")
        self.assertEqual(attachments[0].get_content_type(), "application/pdf")


if __name__ == "__main__":
    unittest.main()
