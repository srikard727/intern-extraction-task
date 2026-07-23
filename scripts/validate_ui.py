from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_rfq_extractor.api import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the lightweight RFQ output UI.")
    parser.add_argument("--db", default="outputs/rfq_extractions.db")
    parser.add_argument("--json", default="outputs/rfq_extractions.json")
    parser.add_argument("--detail-email", default="fixture-019")
    parser.add_argument("--fixture-expectations", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    client = TestClient(
        create_app(
            db_path=args.db,
            database_url="",
            json_path=args.json,
            project_root=PROJECT_ROOT,
        )
    )

    _check_health(client, errors)
    emails = _email_summaries(client, errors)
    detail_email = _choose_detail_email(emails, args.detail_email)

    _check_page(
        client,
        "/view",
        ["Review Dashboard", "Email Queue", "Emails", "Items", "Human Review", "Attachments"],
        errors,
    )
    _check_page(
        client,
        "/view?status=human_review_required",
        ["Review Dashboard", "Email Queue", "human_review_required"],
        errors,
    )
    _check_page(
        client,
        "/view?glass_type=insulated",
        ["Review Dashboard", "Glass Type", "insulated"],
        errors,
    )
    if detail_email:
        _check_page(
            client,
            f"/view/emails/{detail_email}",
            ["Email Detail", "Email", "Attachments", "Human Review", "Agent Runs"],
            errors,
        )
    else:
        errors.append("no email record found for detail view validation")

    if args.fixture_expectations:
        _check_page(
            client,
            "/view/emails/fixture-019",
            ["fixture-019", "Laminated-Insulated", "HT3", "Agent Runs"],
            errors,
        )
        _check_page(
            client,
            "/view/emails/fixture-023",
            ["fixture-023", "Human Review", "No glass units extracted."],
            errors,
        )

    if errors:
        print("UI validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("UI validation passed.")
    print(f"Checked {len(emails)} email summary record(s).")
    if detail_email:
        print(f"Detail page checked: {detail_email}")
    return 0


def _check_health(client: TestClient, errors: list[str]) -> None:
    response = client.get("/health")
    if response.status_code != 200:
        errors.append(f"GET /health returned {response.status_code}")
        return
    data = response.json()
    counts = data.get("counts") if isinstance(data, dict) else {}
    if not isinstance(counts, dict) or counts.get("emails", 0) < 1:
        errors.append("/health did not report any stored email records")


def _email_summaries(client: TestClient, errors: list[str]) -> list[dict[str, Any]]:
    response = client.get("/emails?limit=500")
    if response.status_code != 200:
        errors.append(f"GET /emails returned {response.status_code}")
        return []
    emails = response.json().get("emails", [])
    if not isinstance(emails, list):
        errors.append("GET /emails did not return an emails list")
        return []
    return [email for email in emails if isinstance(email, dict)]


def _choose_detail_email(emails: list[dict[str, Any]], preferred: str) -> str | None:
    ids = [str(email.get("email_id") or "") for email in emails]
    if preferred in ids:
        return preferred
    return ids[0] if ids else None


def _check_page(
    client: TestClient,
    path: str,
    expected_text: list[str],
    errors: list[str],
) -> None:
    response = client.get(path)
    if response.status_code != 200:
        errors.append(f"GET {path} returned {response.status_code}")
        return
    for text in expected_text:
        if text not in response.text:
            errors.append(f"GET {path} missing text: {text}")


if __name__ == "__main__":
    raise SystemExit(main())
