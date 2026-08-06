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


OUT_PATH = Path("reports/WSR_RFQ_Extraction_Status_Report_2026-08-06.docx")


TODAY_ROWS = [
    [
        "Docker Desktop / daemon",
        "Started Docker Desktop and confirmed `docker info` succeeded.",
    ],
    [
        "Final QA with Docker build",
        "Ran `.venv/bin/python scripts/final_qa.py --docker-build`; unit tests, compile check, JSON/SQLite audit, UI validation, Compose config, and image build all passed.",
    ],
    [
        "Docker Compose stack",
        "Ran `docker compose up --build -d`; PostgreSQL, Redis, FastAPI API, and Celery worker started successfully.",
    ],
    [
        "Containerized API/UI",
        "Verified containerized `/health` and `/view` on `http://127.0.0.1:8000`.",
    ],
    [
        "Synchronous Docker extraction",
        "Triggered `POST /extract/fixture` through the containerized API and confirmed one fixture email extracted successfully into PostgreSQL.",
    ],
    [
        "Queued Docker extraction",
        "Triggered `POST /tasks/extract/fixture`; Redis/Celery worker completed the task successfully.",
    ],
    [
        "PostgreSQL persistence",
        "Confirmed validation row counts inside PostgreSQL: `emails=1`, `items=1`, and `agent_runs=1`.",
    ],
    [
        "Docs",
        "Updated README, deployment guide, and final demo notes with the successful August 6 Docker validation.",
    ],
]


VALIDATION_ROWS = [
    ["Unit tests", "Passed: 43 tests."],
    ["Compile check", "Passed for agent_rfq_extractor, database, scripts, and tests."],
    ["Local JSON/SQLite audit", "Passed: 28 email records, 40 extracted items, and 28 agent runs."],
    ["UI validation", "Passed against the local fixture output database."],
    ["Docker Compose config", "Passed."],
    ["Docker image build", "Passed with image tag `glass-rfq-extractor:local-qa`."],
    ["Docker Compose startup", "Passed with PostgreSQL, Redis, API, and worker running."],
    ["Containerized sync extraction", "Passed with one fixture email extracted through FastAPI into PostgreSQL."],
    ["Containerized Celery extraction", "Passed with one queued fixture email extraction through Redis and the worker."],
]


REQUIREMENT_ROWS = [
    ["C5", "Docker Compose Setup", "Completed", "Compose build/startup now validated end to end."],
    ["H4", "Celery Worker Tests", "Completed locally", "Unit-level Celery task tests pass and live Redis/worker task execution was validated in Docker."],
    ["I3", "Docker Build Pipeline", "Completed locally", "Docker image build passed locally and CI workflow includes Docker build job."],
    ["I4", "DevOps Testing and Improvements", "Mostly complete", "Local DevOps validation passed; GitHub Actions still needs to run after push."],
    ["J1", "Final Testing", "Mostly complete", "Local final QA and Docker validation passed; final GitHub CI confirmation remains."],
]


NOTE_ROWS = [
    [
        "Why Docker shows one email",
        "The Docker/PostgreSQL validation intentionally used `limit=1` with `replace_existing=true` to validate the full platform path quickly without rerunning all fixture emails through the LLM.",
    ],
    [
        "Full fixture output remains available",
        "The local SQLite/JSON fixture outputs were restored and audited after Docker validation. They still contain 28 emails, 40 extracted items, and 28 agent runs.",
    ],
    [
        "How to populate Docker with all fixtures",
        "Run `POST /extract/fixture` with `limit=100` and `replace_existing=true` if the Docker/PostgreSQL dashboard needs all 28 fixture emails.",
    ],
]


NEXT_ROWS = [
    ["1", "Push to GitHub", "Confirm the GitHub Actions test and Docker jobs pass remotely."],
    ["2", "Optional full Docker fixture run", "Populate PostgreSQL with all 28 fixture emails if the demo needs the Docker `/view` to show the full dataset."],
    ["3", "Demo walkthrough", "Use docs/final_demo.md to present local extraction, audit, UI, Docker API, and Celery queue validation."],
]


def document_xml() -> str:
    body: list[str] = []
    body.append(para("WEEKLY STATUS REPORT", style="Title", after=80, keep_next=True))
    body.append(para("Glass RFQ Extraction System - August 6 Docker and QA Update", style="Subtitle", after=220))
    body.append(label_para("Prepared for", "Bilvantis Internship Project"))
    body.append(label_para("Prepared by", "Srikar Devesetti"))
    body.append(label_para("Report date", "August 6, 2026"))
    body.append(label_para("Reporting window", "August 6, 2026"))
    body.append(label_para("Reporting focus", "Docker validation, Celery validation, final QA, and remaining follow-up"))
    body.append(
        callout(
            "Executive Summary",
            "Today the remaining Docker-related validation was completed. Docker Desktop was started, final QA passed with Docker image build enabled, Docker Compose successfully launched PostgreSQL, Redis, FastAPI, and Celery worker services, and both synchronous API extraction and queued Celery extraction were validated against PostgreSQL. The Docker database shows one reviewed email because the platform validation intentionally used a one-email fixture run; the full local SQLite/JSON fixture output remains 28 emails, 40 extracted items, and 28 agent runs.",
        )
    )

    body.append(para("Work Completed Today", style="Heading1", keep_next=True))
    body.append(table(["Area", "Update"], TODAY_ROWS, [2400, 6960]))

    body.append(para("Validation Evidence", style="Heading1", keep_next=True))
    body.append(table(["Check", "Result"], VALIDATION_ROWS, [2500, 6860]))

    body.append(para("One-Email Docker Validation Note", style="Heading1", keep_next=True))
    body.append(table(["Topic", "Explanation"], NOTE_ROWS, [2600, 6760]))

    body.append(para("Requirement Impact", style="Heading1", keep_next=True))
    body.append(table(["ID", "Requirement", "Status", "Evidence"], REQUIREMENT_ROWS, [650, 2600, 1700, 4410]))

    body.append(para("Remaining Follow-Up", style="Heading1", keep_next=True))
    body.append(table(["#", "Action", "Reason"], NEXT_ROWS, [650, 2700, 6010]))

    body.append(para("Overall Assessment", style="Heading1", keep_next=True))
    body.append(
        callout(
            "Current position",
            "The project is locally validated across extraction output, API/UI, PostgreSQL persistence, Redis/Celery queueing, Docker Compose, and Docker image build. No requirement remains completely unstarted. The main open confirmation is remote GitHub Actions after the branch is pushed.",
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
