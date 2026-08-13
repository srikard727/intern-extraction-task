from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from agent_rfq_extractor.agents.base import AgentResult
from agent_rfq_extractor.models import EmailRecord, RFQItem


class StorageError(RuntimeError):
    pass


class ExtractionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
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

            CREATE TABLE IF NOT EXISTS agent_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                parent_run_id TEXT,
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL,
                model TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                email_id TEXT,
                conv_id TEXT,
                error TEXT,
                review_status TEXT,
                item_count INTEGER,
                metadata_json TEXT,
                context_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_agent_runs_email_id
                ON agent_runs(email_id);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_name
                ON agent_runs(agent_name);
            CREATE INDEX IF NOT EXISTS idx_agent_runs_started_at
                ON agent_runs(started_at);
            CREATE INDEX IF NOT EXISTS idx_items_email_id
                ON items(email_id);
            CREATE INDEX IF NOT EXISTS idx_items_glass_type
                ON items(glass_type);
            """
        )
        self._ensure_column("items", "shape", "TEXT")
        self._ensure_column("items", "color", "TEXT")
        self._ensure_column("items", "gas_fill", "TEXT")
        self._ensure_column("items", "spec_json", "TEXT")
        self._ensure_column("agent_runs", "parent_run_id", "TEXT")
        self._ensure_column("agent_runs", "model", "TEXT")
        self._ensure_column("agent_runs", "email_id", "TEXT")
        self._ensure_column("agent_runs", "conv_id", "TEXT")
        self._ensure_column("agent_runs", "review_status", "TEXT")
        self._ensure_column("agent_runs", "item_count", "INTEGER")
        self._ensure_column("agent_runs", "metadata_json", "TEXT")
        self._ensure_column("agent_runs", "context_json", "TEXT")
        self.conn.commit()

    def clear(self) -> None:
        try:
            with self.conn:
                self.conn.execute("DELETE FROM items")
                self.conn.execute("DELETE FROM emails")
                self.conn.execute("DELETE FROM agent_runs")
        except sqlite3.Error as exc:
            raise StorageError(f"could not clear SQLite database {self.db_path}: {exc}") from exc

    def record_agent_run(self, result: AgentResult[Any]) -> None:
        email_id = _result_value(result, "email_id")
        conv_id = _result_value(result, "conv_id")
        model = _result_value(result, "llm_model") or _result_value(result, "model")
        review_status = _review_status(result)
        item_count = _item_count(result)
        self.conn.execute(
            """
            INSERT INTO agent_runs (
                run_id, parent_run_id, agent_name, status, model,
                started_at, finished_at, duration_ms, email_id, conv_id,
                error, review_status, item_count, metadata_json, context_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                parent_run_id=excluded.parent_run_id,
                agent_name=excluded.agent_name,
                status=excluded.status,
                model=excluded.model,
                started_at=excluded.started_at,
                finished_at=excluded.finished_at,
                duration_ms=excluded.duration_ms,
                email_id=excluded.email_id,
                conv_id=excluded.conv_id,
                error=excluded.error,
                review_status=excluded.review_status,
                item_count=excluded.item_count,
                metadata_json=excluded.metadata_json,
                context_json=excluded.context_json
            """,
            (
                result.context.run_id,
                result.context.parent_run_id,
                result.agent_name,
                result.status,
                model,
                result.started_at,
                result.finished_at,
                result.duration_ms,
                email_id,
                conv_id,
                result.error,
                review_status,
                item_count,
                _json(result.metadata),
                _json(result.context.model_dump(mode="json")),
            ),
        )
        self.conn.commit()

    def counts(self) -> dict[str, int]:
        return {
            "emails": _count_rows(self.conn, "emails"),
            "items": _count_rows(self.conn, "items"),
            "agent_runs": _count_rows(self.conn, "agent_runs"),
        }

    def list_emails(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
                e.email_id,
                e.conv_id,
                e.from_email,
                e.to_email,
                e.subject,
                e.received_at,
                e.extracted_at,
                e.status,
                e.has_attachments,
                e.llm_model,
                COALESCE(COUNT(i.id), 0) AS item_count
            FROM emails e
            LEFT JOIN items i ON i.email_id = e.email_id
            GROUP BY e.email_id
            ORDER BY e.received_at DESC, e.email_id
            LIMIT ? OFFSET ?
            """,
            (_safe_limit(limit), max(offset, 0)),
        ).fetchall()
        return [_row_dict(row) for row in rows]

    def get_email(self, email_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT raw_json FROM emails WHERE email_id = ?",
            (email_id,),
        ).fetchone()
        if row is None or not row["raw_json"]:
            return None
        return json.loads(row["raw_json"])

    def list_item_sources(self, email_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, mark, glass_type, source, field_sources_json
            FROM items
            WHERE email_id = ?
            ORDER BY id
            """,
            (email_id,),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            data = _row_dict(row)
            data["field_sources"] = _loads_json(
                data.pop("field_sources_json", None),
                default={},
            )
            results.append(data)
        return results

    def list_agent_runs(
        self,
        limit: int = 100,
        offset: int = 0,
        email_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where = "WHERE email_id = ?" if email_id else ""
        params: list[Any] = []
        if email_id:
            params.append(email_id)
        params.extend([_safe_limit(limit), max(offset, 0)])
        rows = self.conn.execute(
            f"""
            SELECT
                run_id,
                parent_run_id,
                agent_name,
                status,
                model,
                started_at,
                finished_at,
                duration_ms,
                email_id,
                conv_id,
                error,
                review_status,
                item_count,
                metadata_json,
                context_json
            FROM agent_runs
            {where}
            ORDER BY started_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [_agent_run_row(row) for row in rows]

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
                run_id,
                parent_run_id,
                agent_name,
                status,
                model,
                started_at,
                finished_at,
                duration_ms,
                email_id,
                conv_id,
                error,
                review_status,
                item_count,
                metadata_json,
                context_json
            FROM agent_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return _agent_run_row(row)

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
        _write_json_atomic(Path(out_path), data)

    def _insert_item(self, email_id: str, item: RFQItem) -> None:
        dimensions = item.dimensions
        spec_json = _json(item.to_jsonable())
        raw_json = _json(item.model_dump(mode="json"))
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
                raw_json,
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
    data = [record.to_jsonable() for record in records]
    _write_json_atomic(Path(out_path), data)


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_json_atomic(out: Path, data: Any) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_name(f".{out.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(out)
    finally:
        temporary.unlink(missing_ok=True)


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _safe_limit(limit: int) -> int:
    return min(max(limit, 1), 500)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    if "has_attachments" in data and data["has_attachments"] is not None:
        data["has_attachments"] = bool(data["has_attachments"])
    return data


def _agent_run_row(row: sqlite3.Row) -> dict[str, Any]:
    data = _row_dict(row)
    data["metadata"] = _loads_json(data.pop("metadata_json", None), default={})
    data["context"] = _loads_json(data.pop("context_json", None), default={})
    return data


def _loads_json(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _result_value(result: AgentResult[Any], key: str) -> Any:
    if key in result.metadata:
        return result.metadata[key]
    if key in result.context.metadata:
        return result.context.metadata[key]
    return getattr(result.output, key, None)


def _review_status(result: AgentResult[Any]) -> str | None:
    output_status = getattr(result.output, "status", None)
    if output_status == "human_review_required":
        return "human_review_required"
    if output_status == "completed":
        return "not_required"
    if output_status == "extraction_failed":
        return "extraction_failed"

    review_required = result.metadata.get("review_required")
    if review_required is True:
        return "human_review_required"
    if review_required is False:
        return "not_required"
    return None


def _item_count(result: AgentResult[Any]) -> int | None:
    metadata_count = result.metadata.get("item_count")
    if isinstance(metadata_count, int):
        return metadata_count

    items = getattr(result.output, "items", None)
    if isinstance(items, list):
        return len(items)
    return None


def _interlayer_summary(item: RFQItem) -> str | None:
    parts = [item.interlayer_thickness, item.interlayer_material]
    summary = " ".join(part for part in parts if part)
    return summary or item.interlayer
