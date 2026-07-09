import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from agent_rfq_extractor.agents import AgentContext, AgentResult
from agent_rfq_extractor.api import create_app
from agent_rfq_extractor.models import EmailRecord
from database.storage import ExtractionStore


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "rfq.db"
        self.json_path = Path(self.tmpdir.name) / "rfq.json"
        (Path(self.tmpdir.name) / "Emails.txt").write_text("Email: 1\nRFQ test", encoding="utf-8")
        self._seed_database()
        self.client = TestClient(
            create_app(
                db_path=self.db_path,
                database_url="",
                json_path=self.json_path,
                project_root=self.tmpdir.name,
            )
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_health_returns_counts(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["counts"]["emails"], 1)
        self.assertEqual(data["counts"]["agent_runs"], 1)

    def test_list_and_get_emails(self):
        list_response = self.client.get("/emails")
        detail_response = self.client.get("/emails/email-001")

        self.assertEqual(list_response.status_code, 200)
        emails = list_response.json()["emails"]
        self.assertEqual(len(emails), 1)
        self.assertEqual(emails[0]["email_id"], "email-001")
        self.assertEqual(emails[0]["item_count"], 0)

        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["email_id"], "email-001")
        self.assertIn("extraction", detail)

    def test_list_and_get_agent_runs(self):
        list_response = self.client.get("/agent-runs")
        detail_response = self.client.get("/agent-runs/run-001")

        self.assertEqual(list_response.status_code, 200)
        runs = list_response.json()["agent_runs"]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "run-001")
        self.assertEqual(runs[0]["metadata"]["email_id"], "email-001")

        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["agent_name"], "extractor")
        self.assertEqual(detail["review_status"], "not_required")

    def test_missing_resources_return_404(self):
        self.assertEqual(self.client.get("/emails/missing").status_code, 404)
        self.assertEqual(self.client.get("/agent-runs/missing").status_code, 404)

    def test_queue_fixture_endpoint_returns_task_id(self):
        with patch("agent_rfq_extractor.api.extract_fixture_task.delay") as delay:
            delay.return_value = SimpleNamespace(id="task-001")

            response = self.client.post(
                "/tasks/extract/fixture",
                json={"fixture_path": "Emails.txt", "limit": 1},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task_id"], "task-001")
        delay.assert_called_once()

    def test_task_status_endpoint_returns_celery_state(self):
        with patch("agent_rfq_extractor.api.celery_app.AsyncResult") as async_result:
            result = async_result.return_value
            result.status = "SUCCESS"
            result.ready.return_value = True
            result.successful.return_value = True
            result.failed.return_value = False
            result.result = {"records": 1}

            response = self.client.get("/tasks/task-001")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["result"], {"records": 1})

    def _seed_database(self):
        record = _record()
        store = ExtractionStore(self.db_path)
        try:
            store.upsert_record(record)
            store.record_agent_run(
                AgentResult[EmailRecord](
                    agent_name="extractor",
                    status="completed",
                    output=record,
                    error=None,
                    started_at="2026-07-08T01:00:00+00:00",
                    finished_at="2026-07-08T01:00:01+00:00",
                    duration_ms=1000,
                    context=AgentContext(
                        run_id="run-001",
                        metadata={"email_id": "email-001", "model": "fake-model"},
                    ),
                    metadata={
                        "email_id": "email-001",
                        "conv_id": "thread-001",
                        "item_count": 0,
                        "review_required": False,
                        "llm_model": "fake-model",
                    },
                )
            )
        finally:
            store.close()


def _record() -> EmailRecord:
    return EmailRecord(
        email_id="email-001",
        conv_id="thread-001",
        from_email="requester@example.com",
        to_email="sales@example.com",
        subject="RFQ",
        body_text='1/4" clear tempered 12 x 24',
        emailbody_variant="plain",
        received_at="2026-07-08T00:00:00+00:00",
        has_attachments=False,
        extracted_at=datetime.now(timezone.utc).isoformat(),
        status="completed",
        items=[],
        review=None,
        attachments=[],
        llm_model="fake-model",
    )


if __name__ == "__main__":
    unittest.main()
