from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from agent_rfq_extractor.models import EmailRecord, RFQItem


class StorageError(RuntimeError):
    pass


class ExtractionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 30000")
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS emails (
                email_id TEXT PRIMARY KEY,
                conv_id TEXT,
                from_email TEXT,
                to_email TEXT,
                subject TEXT,
                body_text TEXT,
                emailbody_variant TEXT,
                received_at TEXT,
                has_attachments INTEGER,
                extracted_at TEXT,
                status TEXT,
                review_json TEXT,
                attachments_json TEXT,
                llm_model TEXT,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT NOT NULL,
                mark TEXT,
                width REAL,
                height REAL,
                quantity INTEGER,
                shape TEXT,
                TK TEXT,
                HT TEXT,
                TT TEXT,
                color TEXT,
                glass_type TEXT,
                airspace TEXT,
                overall_thickness TEXT,
                gas_fill TEXT,
                coating TEXT,
                edge_work TEXT,
                interlayer TEXT,
                lite_details_json TEXT,
                source TEXT,
                field_sources_json TEXT,
                missing_fields_json TEXT,
                notes TEXT,
                spec_json TEXT,
                raw_json TEXT,
                FOREIGN KEY(email_id) REFERENCES emails(email_id)
            );
            """
        )
        self._ensure_column("items", "shape", "TEXT")
        self._ensure_column("items", "color", "TEXT")
        self._ensure_column("items", "gas_fill", "TEXT")
        self._ensure_column("items", "spec_json", "TEXT")
        self.conn.commit()

    def clear(self) -> None:
        try:
            with self.conn:
                self.conn.execute("DELETE FROM items")
                self.conn.execute("DELETE FROM emails")
        except sqlite3.Error as exc:
            raise StorageError(f"could not clear SQLite database {self.db_path}: {exc}") from exc

    def upsert_record(self, record: EmailRecord) -> None:
        review_json = _json(record.review.model_dump(mode="json") if record.review else None)
        attachments_json = _json([att.model_dump(mode="json") for att in record.attachments])
        raw_json = _json(record.to_jsonable())
        self.conn.execute(
            """
            INSERT INTO emails (
                email_id, conv_id, from_email, to_email, subject, body_text,
                emailbody_variant, received_at, has_attachments, extracted_at,
                status, review_json, attachments_json, llm_model, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email_id) DO UPDATE SET
                conv_id=excluded.conv_id,
                from_email=excluded.from_email,
                to_email=excluded.to_email,
                subject=excluded.subject,
                body_text=excluded.body_text,
                emailbody_variant=excluded.emailbody_variant,
                received_at=excluded.received_at,
                has_attachments=excluded.has_attachments,
                extracted_at=excluded.extracted_at,
                status=excluded.status,
                review_json=excluded.review_json,
                attachments_json=excluded.attachments_json,
                llm_model=excluded.llm_model,
                raw_json=excluded.raw_json
            """,
            (
                record.email_id,
                record.conv_id,
                record.from_email,
                record.to_email,
                record.subject,
                record.body_text,
                record.emailbody_variant,
                record.received_at,
                int(record.has_attachments),
                record.extracted_at,
                record.status,
                review_json,
                attachments_json,
                record.llm_model,
                raw_json,
            ),
        )
        self.conn.execute("DELETE FROM items WHERE email_id = ?", (record.email_id,))
        for item in record.items:
            self._insert_item(record.email_id, item)
        self.conn.commit()

    def export_json(self, out_path: str | Path) -> None:
        rows = self.conn.execute(
            "SELECT raw_json FROM emails ORDER BY received_at DESC, email_id"
        ).fetchall()
        data = [json.loads(row["raw_json"]) for row in rows if row["raw_json"]]
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _insert_item(self, email_id: str, item: RFQItem) -> None:
        dimensions = item.dimensions
        spec_json = _json(item.to_jsonable())
        self.conn.execute(
            """
            INSERT INTO items (
                email_id, mark, width, height, quantity, shape, TK, HT, TT, color, glass_type,
                airspace, overall_thickness, gas_fill, coating, edge_work, interlayer,
                lite_details_json, source, field_sources_json,
                missing_fields_json, notes, spec_json, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email_id,
                item.mark,
                dimensions.width if dimensions else None,
                dimensions.height if dimensions else None,
                item.quantity,
                item.shape,
                item.TK,
                item.HT,
                item.TT,
                item.color,
                item.glass_type,
                item.spacer_thickness,
                item.overall_thickness,
                item.gas_fill,
                item.coating,
                item.edge_work,
                _interlayer_summary(item),
                _json(item.lite_details),
                item.source,
                _json(item.field_sources),
                _json(item.missing_fields),
                item.notes,
                spec_json,
                spec_json,
            ),
        )

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def write_json(records: Iterable[EmailRecord], out_path: str | Path) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = [record.to_jsonable() for record in records]
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _interlayer_summary(item: RFQItem) -> str | None:
    parts = [item.interlayer_thickness, item.interlayer_material]
    summary = " ".join(part for part in parts if part)
    return summary or item.interlayer
