from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from agent_rfq_extractor.agents.base import AgentResult
from agent_rfq_extractor.models import EmailRecord, RFQItem

from .storage import StorageError


class PostgresExtractionStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.conn = psycopg.connect(database_url, row_factory=dict_row)
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        schema_path = Path(__file__).with_name("postgres_schema.sql")
        try:
            self.conn.execute(schema_path.read_text(encoding="utf-8"))
            self.conn.commit()
        except psycopg.Error as exc:
            self.conn.rollback()
            raise StorageError(f"could not initialize PostgreSQL schema: {exc}") from exc

    def clear(self) -> None:
        try:
            self.conn.execute("DELETE FROM items")
            self.conn.execute("DELETE FROM emails")
            self.conn.execute("DELETE FROM agent_runs")
            self.conn.commit()
        except psycopg.Error as exc:
            self.conn.rollback()
            raise StorageError(f"could not clear PostgreSQL database: {exc}") from exc

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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                Jsonb(result.metadata),
                Jsonb(result.context.model_dump(mode="json")),
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
            LIMIT %s OFFSET %s
            """,
            (_safe_limit(limit), max(offset, 0)),
        ).fetchall()
        return [_row_dict(row) for row in rows]

    def get_email(self, email_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT raw_json FROM emails WHERE email_id = %s",
            (email_id,),
        ).fetchone()
        if row is None or row["raw_json"] is None:
            return None
        return row["raw_json"]

    def list_agent_runs(
        self,
        limit: int = 100,
        offset: int = 0,
        email_id: str | None = None,
    ) -> list[dict[str, Any]]:
        where = "WHERE email_id = %s" if email_id else ""
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
            LIMIT %s OFFSET %s
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
            WHERE run_id = %s
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return _agent_run_row(row)

    def upsert_record(self, record: EmailRecord) -> None:
        review_json = record.review.model_dump(mode="json") if record.review else None
        attachments_json = [att.model_dump(mode="json") for att in record.attachments]
        raw_json = record.to_jsonable()
        self.conn.execute(
            """
            INSERT INTO emails (
                email_id, conv_id, from_email, to_email, subject, body_text,
                emailbody_variant, received_at, has_attachments, extracted_at,
                status, review_json, attachments_json, llm_model, raw_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                record.has_attachments,
                record.extracted_at,
                record.status,
                Jsonb(review_json) if review_json is not None else None,
                Jsonb(attachments_json),
                record.llm_model,
                Jsonb(raw_json),
            ),
        )
        self.conn.execute("DELETE FROM items WHERE email_id = %s", (record.email_id,))
        for item in record.items:
            self._insert_item(record.email_id, item)
        self.conn.commit()

    def export_json(self, out_path: str | Path) -> None:
        rows = self.conn.execute(
            "SELECT raw_json FROM emails ORDER BY received_at DESC, email_id"
        ).fetchall()
        data = [row["raw_json"] for row in rows if row["raw_json"] is not None]
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _insert_item(self, email_id: str, item: RFQItem) -> None:
        dimensions = item.dimensions
        spec_json = item.to_jsonable()
        self.conn.execute(
            """
            INSERT INTO items (
                email_id, mark, width, height, quantity, shape, TK, HT, TT, color, glass_type,
                airspace, overall_thickness, gas_fill, coating, edge_work, interlayer,
                lite_details_json, source, field_sources_json,
                missing_fields_json, notes, spec_json, raw_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                Jsonb(item.lite_details),
                item.source,
                Jsonb(item.field_sources),
                Jsonb(item.missing_fields),
                item.notes,
                Jsonb(spec_json),
                Jsonb(spec_json),
            ),
        )


def _count_rows(conn, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _safe_limit(limit: int) -> int:
    return min(max(limit, 1), 500)


def _row_dict(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _agent_run_row(row: dict[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["metadata"] = data.pop("metadata_json", None) or {}
    data["context"] = data.pop("context_json", None) or {}
    return data


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
