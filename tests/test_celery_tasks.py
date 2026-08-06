import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent_rfq_extractor.tasks import extract_fixture_task, extract_gmail_task


class CeleryTaskTests(unittest.TestCase):
    def test_fixture_task_executes_pipeline_and_returns_summary(self):
        with patch("agent_rfq_extractor.tasks.RFQPipeline", FakePipeline):
            result = extract_fixture_task.apply(
                kwargs={
                    "fixture_path": "Emails.txt",
                    "limit": 2,
                    "replace_existing": True,
                    "model": "fake-model",
                }
            ).get(propagate=True)

        pipeline = FakePipeline.instances[-1]
        self.assertTrue(pipeline.validated)
        self.assertTrue(pipeline.closed)
        self.assertEqual(pipeline.fixture_args, ("Emails.txt", 2))
        self.assertEqual(result["records"], 2)
        self.assertEqual(result["statuses"], {"completed": 1, "human_review_required": 1})
        self.assertEqual(result["emails"], ["fixture-001", "fixture-002"])
        self.assertEqual(result["database"], "sqlite:///fake.db")
        self.assertEqual(result["json_output"], "fake.json")

    def test_gmail_task_uses_explicit_message_ids_when_provided(self):
        with patch("agent_rfq_extractor.tasks.RFQPipeline", FakePipeline):
            result = extract_gmail_task.apply(
                kwargs={
                    "query": "subject:RFQ",
                    "limit": 10,
                    "email_ids": ["gmail-001", "gmail-002"],
                    "credentials_path": "credentials.json",
                    "token_path": "token.json",
                }
            ).get(propagate=True)

        pipeline = FakePipeline.instances[-1]
        self.assertEqual(
            pipeline.gmail_ids_args,
            (["gmail-001", "gmail-002"], "credentials.json", "token.json"),
        )
        self.assertIsNone(pipeline.gmail_args)
        self.assertEqual(result["emails"], ["gmail-001", "gmail-002"])

    def test_gmail_task_uses_search_query_without_message_ids(self):
        with patch("agent_rfq_extractor.tasks.RFQPipeline", FakePipeline):
            result = extract_gmail_task.apply(
                kwargs={
                    "query": "subject:RFQ",
                    "limit": 5,
                    "email_ids": [],
                    "credentials_path": "credentials.json",
                    "token_path": "token.json",
                }
            ).get(propagate=True)

        pipeline = FakePipeline.instances[-1]
        self.assertEqual(pipeline.gmail_args, ("subject:RFQ", 5, "credentials.json", "token.json"))
        self.assertIsNone(pipeline.gmail_ids_args)
        self.assertEqual(result["emails"], ["gmail-search-001"])

    def test_task_closes_pipeline_when_validation_fails(self):
        FakePipeline.fail_validation = True
        try:
            with patch("agent_rfq_extractor.tasks.RFQPipeline", FakePipeline):
                with self.assertRaises(RuntimeError):
                    extract_fixture_task.apply(kwargs={"fixture_path": "Emails.txt"}).get(propagate=True)
        finally:
            FakePipeline.fail_validation = False

        self.assertTrue(FakePipeline.instances[-1].closed)


class FakePipeline:
    instances: list["FakePipeline"] = []
    fail_validation = False

    def __init__(
        self,
        db_path,
        json_path,
        model=None,
        replace_existing=False,
        database_url=None,
    ):
        self.db_path = db_path
        self.json_path = Path("fake.json")
        self.model = model
        self.replace_existing = replace_existing
        self.database_url = database_url
        self.database_label = "sqlite:///fake.db"
        self.validated = False
        self.closed = False
        self.fixture_args = None
        self.gmail_args = None
        self.gmail_ids_args = None
        self.instances.append(self)

    def validate_llm(self):
        self.validated = True
        if self.fail_validation:
            raise RuntimeError("validation failed")

    def run_fixture(self, fixture_path, limit=None):
        self.fixture_args = (fixture_path, limit)
        return [
            SimpleNamespace(email_id="fixture-001", status="completed"),
            SimpleNamespace(email_id="fixture-002", status="human_review_required"),
        ][:limit]

    def run_gmail(self, query, limit, credentials_path=None, token_path=None):
        self.gmail_args = (query, limit, credentials_path, token_path)
        return [SimpleNamespace(email_id="gmail-search-001", status="completed")]

    def run_gmail_ids(self, message_ids, credentials_path=None, token_path=None):
        self.gmail_ids_args = (message_ids, credentials_path, token_path)
        return [SimpleNamespace(email_id=message_id, status="completed") for message_id in message_ids]

    def close(self):
        self.closed = True


if __name__ == "__main__":
    unittest.main()
