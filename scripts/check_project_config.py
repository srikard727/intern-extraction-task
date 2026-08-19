from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_rfq_extractor.claude_client import DEFAULT_MODEL  # noqa: E402


EXPECTED_MODEL = "claude-opus-4-8"


def main() -> int:
    errors: list[str] = []

    if DEFAULT_MODEL != EXPECTED_MODEL:
        errors.append(f"default Anthropic model is {DEFAULT_MODEL}, expected {EXPECTED_MODEL}")

    example = dotenv_values(PROJECT_ROOT / ".env.example")
    if example.get("ANTHROPIC_MODEL") != EXPECTED_MODEL:
        errors.append(".env.example does not default ANTHROPIC_MODEL to Opus")
    if example.get("RFQ_DB_PATH") != "outputs/rfq_extractions.db":
        errors.append(".env.example points RFQ_DB_PATH at a non-canonical database")
    if example.get("RFQ_JSON_PATH") != "outputs/rfq_extractions.json":
        errors.append(".env.example points RFQ_JSON_PATH at a non-canonical JSON export")

    local_env_path = PROJECT_ROOT / ".env"
    if local_env_path.exists():
        local_env = dotenv_values(local_env_path)
        if local_env.get("ANTHROPIC_MODEL") != EXPECTED_MODEL:
            errors.append("local .env does not use the Opus default")
        if local_env.get("RFQ_DB_PATH") not in (None, "outputs/rfq_extractions.db"):
            errors.append("local .env points RFQ_DB_PATH at a non-canonical database")

    _require_patterns(
        PROJECT_ROOT / ".gitignore",
        {".env", ".env.*", "credentials*.json", "token*.json", "~$*.docx"},
        errors,
    )
    _require_patterns(
        PROJECT_ROOT / ".dockerignore",
        {".env*", "credentials*.json", "token*.json", ".git", ".venv", "*.db"},
        errors,
    )

    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    if "required: false" not in compose:
        errors.append("Docker Compose still requires a local .env during CI validation")
    if "--reload" in compose:
        errors.append("Docker Compose API command must not use development reload mode")
    if "- .:/app" in compose:
        errors.append("Docker Compose bind-mounts the repository and bypasses image isolation")
    if "--concurrency=2" not in compose:
        errors.append("Celery worker concurrency is not capped for the demo workload")
    if compose.count("rfq_outputs:/app/outputs") < 2:
        errors.append("API and worker do not share the persistent RFQ output volume")
    for port in ("5432", "6379", "8000"):
        if f'"127.0.0.1:{port}:{port}"' not in compose:
            errors.append(f"Docker Compose port {port} is not restricted to localhost")
    if "USER app" not in dockerfile or "COPY --chown=app:app" not in dockerfile:
        errors.append("Docker image does not run application processes as an unprivileged user")
    if "tesseract-ocr" not in dockerfile:
        errors.append("Docker image does not install the image-only attachment OCR runtime")

    gmail_override_path = PROJECT_ROOT / "docker-compose.gmail.yml"
    if not gmail_override_path.exists():
        errors.append("Docker Gmail credential override is missing")
    else:
        gmail_override = gmail_override_path.read_text(encoding="utf-8")
        if gmail_override.count("read_only: true") < 4:
            errors.append("Docker Gmail credentials are not mounted read-only for API and worker")
        if gmail_override.count("/run/secrets/") < 8:
            errors.append("Docker Gmail credentials are not isolated under /run/secrets")

    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if "workflow_dispatch:" not in workflow:
        errors.append("GitHub Actions workflow is not manually runnable")
    if "tesseract-ocr" not in workflow:
        errors.append("GitHub Actions does not install the OCR runtime before tests")

    _check_tracked_sensitive_files(errors)

    if errors:
        print("Project configuration check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Project configuration check passed.")
    print(f"Default model: {EXPECTED_MODEL}")
    print("Canonical outputs: outputs/rfq_extractions.db and outputs/rfq_extractions.json")
    return 0


def _require_patterns(path: Path, required: set[str], errors: list[str]) -> None:
    patterns = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    missing = sorted(required - patterns)
    if missing:
        errors.append(f"{path.name} is missing: {', '.join(missing)}")


def _check_tracked_sensitive_files(errors: list[str]) -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        errors.append("could not inspect tracked files with git ls-files")
        return

    unsafe: list[str] = []
    for relative in result.stdout.splitlines():
        path = PROJECT_ROOT / relative
        if not path.exists():
            continue
        name = path.name.lower()
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            unsafe.append(relative)
        elif name.startswith("credentials") and name.endswith(".json"):
            unsafe.append(relative)
        elif name.startswith("token") and name.endswith(".json"):
            unsafe.append(relative)
        elif name.startswith("~$"):
            unsafe.append(relative)
    if unsafe:
        errors.append("sensitive or temporary files are tracked: " + ", ".join(sorted(unsafe)))


if __name__ == "__main__":
    raise SystemExit(main())
