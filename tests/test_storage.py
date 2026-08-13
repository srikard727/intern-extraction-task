import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent_rfq_extractor.models import Dimensions, EmailRecord, RFQItem
from database.storage import ExtractionStore


class StorageTests(unittest.TestCase):
    def test_item_sources_and_internal_raw_item_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ExtractionStore(Path(tmpdir) / "rfq.db")
            try:
                store.upsert_record(_record())

                sources = store.list_item_sources("email-001")
                raw_item = store.conn.execute(
                    "SELECT raw_json FROM items WHERE email_id = ?",
                    ("email-001",),
                ).fetchone()["raw_json"]

                self.assertEqual(sources[0]["field_sources"]["TK"], "body")
                self.assertEqual(json.loads(raw_item)["field_sources"]["TK"], "body")
            finally:
                store.close()

    def test_sqlite_foreign_keys_reject_orphan_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ExtractionStore(Path(tmpdir) / "rfq.db")
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    store.conn.execute(
                        "INSERT INTO items (email_id, quantity, shape) VALUES (?, ?, ?)",
                        ("missing-email", 1, "rectangle"),
                    )
            finally:
                store.close()

    def test_json_export_is_complete_and_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            store = ExtractionStore(root / "rfq.db")
            output = root / "rfq.json"
            try:
                store.upsert_record(_record())
                store.export_json(output)

                data = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(data[0]["email_id"], "email-001")
                self.assertEqual(list(root.glob(".rfq.json.*.tmp")), [])
            finally:
                store.close()


def _record() -> EmailRecord:
    item = RFQItem(
        dimensions=Dimensions(width=24, height=36),
        quantity=1,
        shape="rectangle",
        glass_type="monolithic",
        TK='1/4"',
        HT="tempered",
        TT="clear",
        source="body",
        field_sources={
            "dimensions": "body",
            "quantity": "body",
            "shape": "body",
            "glass_type": "body",
            "TK": "body",
            "HT": "body",
            "TT": "body",
        },
    )
    return EmailRecord(
        email_id="email-001",
        conv_id="thread-001",
        from_email="requester@example.com",
        to_email="sales@example.com",
        subject="RFQ",
        body_text='1/4" clear tempered 24 x 36',
        emailbody_variant="plain",
        received_at=None,
        has_attachments=False,
        extracted_at=datetime.now(timezone.utc).isoformat(),
        status="completed",
        items=[item],
        review=None,
        attachments=[],
        llm_model="fake-model",
    )


if __name__ == "__main__":
    unittest.main()
