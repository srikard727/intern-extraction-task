import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.factory import create_store, storage_label
from database.storage import ExtractionStore


class DatabaseFactoryTests(unittest.TestCase):
    def test_default_store_is_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rfq.db"
            store = create_store(path, database_url=None)
            try:
                self.assertIsInstance(store, ExtractionStore)
                self.assertEqual(store.counts(), {"emails": 0, "items": 0, "agent_runs": 0})
            finally:
                store.close()

    def test_sqlite_database_url_uses_sqlite_store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rfq.db"
            store = create_store(database_url=f"sqlite:///{path}")
            try:
                self.assertIsInstance(store, ExtractionStore)
            finally:
                store.close()

    def test_postgres_database_url_uses_postgres_store(self):
        with patch("database.postgres.PostgresExtractionStore") as store_cls:
            store = create_store(database_url="postgresql://rfq:rfq@localhost:5432/rfq")

        store_cls.assert_called_once_with("postgresql://rfq:rfq@localhost:5432/rfq")
        self.assertEqual(store, store_cls.return_value)

    def test_storage_label_hides_credentials_for_postgres(self):
        label = storage_label(database_url="postgresql://rfq:secret@localhost:5432/rfq")

        self.assertEqual(label, "postgresql://localhost:5432/rfq")

    def test_env_database_url_can_be_ignored_with_empty_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "rfq.db"
            with patch.dict(os.environ, {"DATABASE_URL": "postgresql://example/db"}):
                store = create_store(path, database_url="")
            try:
                self.assertIsInstance(store, ExtractionStore)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
