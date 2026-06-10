from __future__ import annotations

import argparse
import os
from collections import Counter

from dotenv import load_dotenv

from .claude_client import DEFAULT_MODEL
from .pipeline import RFQPipeline


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Extract structured glass RFQs from Gmail.")
    parser.add_argument("--source", choices=["gmail", "fixture"], default="gmail")
    parser.add_argument("--fixture", default="Emails.txt", help="Fixture file for --source fixture.")
    parser.add_argument("--limit", type=int, default=int(os.getenv("RFQ_LIMIT", "30")))
    parser.add_argument(
        "--query",
        default=os.getenv(
            "GMAIL_QUERY",
            'in:inbox newer_than:30d {subject:RFQ subject:"Request for Quote"}',
        ),
        help="Gmail search query used when --source gmail.",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("RFQ_DB_PATH", "outputs/rfq_extractions.db"),
        help="SQLite output path.",
    )
    parser.add_argument("--json", default="outputs/rfq_extractions.json", help="JSON export path.")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Clear existing rows from the target SQLite database before this run.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL),
        help="Anthropic model id.",
    )
    parser.add_argument(
        "--credentials",
        default=os.getenv("GMAIL_CREDENTIALS", "credentials.json"),
        help="Gmail OAuth client credentials path.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GMAIL_TOKEN", "token_reader.json"),
        help="Gmail OAuth token path.",
    )
    args = parser.parse_args()

    pipeline = RFQPipeline(
        db_path=args.db,
        json_path=args.json,
        model=args.model,
        replace_existing=args.replace_existing,
    )
    try:
        if args.source == "gmail":
            print(f"Fetching up to {args.limit} Gmail messages with query: {args.query}")
            records = pipeline.run_gmail(
                query=args.query,
                limit=args.limit,
                credentials_path=args.credentials,
                token_path=args.token,
            )
        else:
            print(f"Reading up to {args.limit} fixture emails from: {args.fixture}")
            records = pipeline.run_fixture(args.fixture, limit=args.limit)
    finally:
        pipeline.close()

    counts = Counter(record.status for record in records)
    print("\nDone.")
    print(f"Model: {args.model}")
    print(f"SQLite: {args.db}")
    print(f"JSON: {args.json}")
    print("Statuses: " + ", ".join(f"{status}={count}" for status, count in sorted(counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
