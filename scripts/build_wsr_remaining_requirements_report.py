from __future__ import annotations

import zipfile
from pathlib import Path

from build_feature_status_wsr_report import (
    NS,
    R_NS,
    callout,
    content_types_xml,
    document_rels_xml,
    label_para,
    para,
    rels_xml,
    settings_xml,
    styles_xml,
    table,
)


OUT_PATH = Path("reports/WSR_RFQ_Extraction_Status_Report_2026-07-23.docx")


COMPLETED_ROWS = [
    [
        "UI requirements",
        "G1/G2/G3/G4/G5 advanced with a FastAPI review dashboard, filters, email detail pages, attachment info, extracted units, missing fields, human-review flags, and UI validation.",
    ],
    [
        "Attachment coverage",
        "Added fixture-style tests for TXT, CSV, DOCX, text-layer PDF, and unsupported image attachments. Image-only/OCR remains out of scope.",
    ],
    [
        "CI / DevOps",
        "Added GitHub Actions workflow for unit tests, compile checks, JSON/SQLite audit, UI validation, Docker Compose config, and Docker image build.",
    ],
    [
        "Final QA tooling",
        "Added scripts/final_qa.py and scripts/validate_ui.py so local QA and UI checks can be repeated consistently.",
    ],
    [
        "Documentation",
        "Added architecture and deployment docs; updated API, platform, final demo, and README instructions.",
    ],
    [
        "Runtime config",
        "Fixed dotenv behavior so explicit environment variables override .env values, which is required for Docker/PostgreSQL deployment correctness.",
    ],
]


VALIDATION_ROWS = [
    ["Unit tests", "Passed: 38 tests via unittest discovery."],
    ["Compile check", "Passed for agent_rfq_extractor, database, scripts, and tests."],
    ["JSON/SQLite audit", "Passed: 28 email records, 40 extracted items, and 28 agent run logs."],
    ["UI validation", "Passed against /view and detail routes using the stored fixture output database."],
    ["FastAPI smoke check", "Passed: /health points to outputs/rfq_extractions.db and reports 28 emails, 40 items, and 28 agent runs."],
    ["Docker Compose config", "Passed: docker compose config --quiet."],
    ["Docker build / live Compose", "Blocked: Docker daemon/Desktop was not running, so image build and docker compose up --build could not be completed in this session."],
]


REMAINING_ROWS = [
    [
        "Docker Compose end-to-end validation",
        "Next",
        "Code and Compose config are ready. Start Docker Desktop, then run docker build and docker compose up --build; verify /health and /view.",
    ],
    [
        "GitHub CI run",
        "Next",
        "Workflow file is added locally. Push the branch to GitHub and confirm the CI test and Docker jobs pass.",
    ],
    [
        "Celery worker tests",
        "Partial",
        "Celery infrastructure and API task endpoints are covered, but deeper live Redis/worker execution tests should be added for H4.",
    ],
    [
        "Attachment/OCR scope",
        "Documented out of scope",
        "Text attachments are covered. Image-only/OCR remains a stretch item unless the assignment requires OCR.",
    ],
    [
        "Final demo walkthrough",
        "Next",
        "Docs and demo steps exist. Do one clean final run after Docker is available and record any final findings.",
    ],
]


COMMAND_ROWS = [
    ["Start Docker validation", "docker build -t glass-rfq-extractor:local-qa ."],
    ["Run platform", "docker compose up --build"],
    ["Check API", "http://127.0.0.1:8000/health"],
    ["Check UI", "http://127.0.0.1:8000/view"],
    ["Local QA", ".venv/bin/python scripts/final_qa.py"],
    ["UI-only validation", ".venv/bin/python scripts/validate_ui.py --db outputs/rfq_extractions.db --json outputs/rfq_extractions.json --fixture-expectations"],
]


def document_xml() -> str:
    body: list[str] = []
    body.append(para("WEEKLY STATUS REPORT", style="Title", after=80, keep_next=True))
    body.append(para("Glass RFQ Extraction System - Remaining Requirements Update", style="Subtitle", after=220))
    body.append(label_para("Prepared for", "Bilvantis Internship Project"))
    body.append(label_para("Prepared by", "Srikar Devesetti"))
    body.append(label_para("Report date", "July 23, 2026"))
    body.append(label_para("Reporting focus", "UI completion, attachment coverage, CI/DevOps setup, final QA, and remaining requirement follow-up"))
    body.append(
        callout(
            "Executive Summary",
            "The visible review UI, attachment test coverage, CI workflow, final QA script, and final documentation polish are now in place. Local validation passed for the Python suite, JSON/SQLite audit, UI route checks, FastAPI smoke check, and Docker Compose configuration. The remaining follow-up is primarily operational: run Docker end-to-end once Docker Desktop is available, push to GitHub and confirm CI, add deeper Celery worker tests if H4 must be fully satisfied, and complete the final demo walkthrough.",
        )
    )

    body.append(para("Completed Since Last WSR", style="Heading1", keep_next=True))
    body.append(table(["Area", "Update"], COMPLETED_ROWS, [2200, 7160]))

    body.append(para("Validation Evidence", style="Heading1", keep_next=True))
    body.append(table(["Check", "Result"], VALIDATION_ROWS, [2300, 7060]))

    body.append(para("Remaining Requirements To Follow", style="Heading1", keep_next=True))
    body.append(table(["Requirement", "Status", "Action Needed"], REMAINING_ROWS, [2600, 1400, 5360]))

    body.append(para("Recommended Next Commands", style="Heading1", keep_next=True))
    body.append(table(["Purpose", "Command / URL"], COMMAND_ROWS, [2300, 7060]))

    body.append(para("Overall Assessment", style="Heading1", keep_next=True))
    body.append(
        callout(
            "Current position",
            "The project is now strong enough for a review/demo from the local fixture outputs. The main caveat is Docker daemon availability; until Docker runs locally or in CI, full platform validation should remain listed as the last open operational requirement.",
        )
    )

    sect = (
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" '
        'w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        '<w:cols w:space="720"/><w:docGrid w:linePitch="360"/></w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{NS}" xmlns:r="{R_NS}"><w:body>'
        + "".join(body)
        + sect
        + "</w:body></w:document>"
    )


def build_docx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types_xml())
        docx.writestr("_rels/.rels", rels_xml())
        docx.writestr("word/_rels/document.xml.rels", document_rels_xml())
        docx.writestr("word/document.xml", document_xml())
        docx.writestr("word/styles.xml", styles_xml())
        docx.writestr("word/settings.xml", settings_xml())


if __name__ == "__main__":
    build_docx(OUT_PATH)
    print(OUT_PATH)
