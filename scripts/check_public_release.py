"""Fail when tracked files contain common public-release hazards."""

from __future__ import annotations

import re
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = (
    re.compile(r"(^|/)\.env(?:\.|$)"),
    re.compile(r"(^|/)(?:credentials|token|client_secret|service-account)[^/]*\.json$", re.I),
    re.compile(r"^data/.*\.(?:db|sqlite|sqlite3)$", re.I),
    re.compile(r"^reports/.*\.docx$", re.I),
    re.compile(r"\.(?:pem|key)$", re.I),
)
SECRET_PATTERNS = {
    "Anthropic API key": re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI-style API key": re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{20,}"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return [entry.decode() for entry in result.stdout.split(b"\0") if entry]


def main() -> int:
    errors: list[str] = []
    files = tracked_files()

    for relative in files:
        if relative != ".env.example" and any(
            pattern.search(relative) for pattern in FORBIDDEN_PATHS
        ):
            errors.append(f"forbidden tracked path: {relative}")
            continue
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > 10_000_000:
            continue
        content = path.read_bytes()
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                errors.append(f"possible {label} in {relative}")

    output_db = ROOT / "outputs" / "rfq_extractions.db"
    if "outputs/rfq_extractions.db" in files and output_db.exists():
        with sqlite3.connect(output_db) as connection:
            rows = connection.execute(
                "SELECT from_email, to_email FROM emails"
            ).fetchall()
        for from_email, to_email in rows:
            for address in (from_email, to_email):
                if address and not address.lower().endswith("@example.com"):
                    errors.append("canonical output database contains a non-example email address")
                    break

    if errors:
        print("Public-release check failed:")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1

    print(f"Public-release check passed ({len(files)} tracked files inspected).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
