from __future__ import annotations

import zipfile
from pathlib import Path

from build_feature_status_wsr_report import (
    NS,
    R_NS,
    callout as base_callout,
    cell,
    label_para,
    para,
    rels_xml,
    settings_xml,
    styles_xml,
)


OUT_PATH = Path("reports/WSR_RFQ_Extraction_Status_Report_2026-08-12.docx")


def callout(title: str, body: str) -> str:
    return base_callout(title, body).replace(
        "<w:tr>",
        "<w:tr><w:trPr><w:cantSplit/></w:trPr>",
        1,
    )


def _table_row(values: list[str], widths: list[int], *, header: bool = False) -> str:
    row_properties = "<w:cantSplit/>"
    if header:
        row_properties += "<w:tblHeader/>"
    fill = "#F2F4F7" if header else None
    cells = "".join(
        cell(
            value,
            width,
            fill=fill,
            bold=header,
            shade_text="#0B2545" if header else None,
            size=9,
        )
        for value, width in zip(values, widths, strict=True)
    )
    return f"<w:tr><w:trPr>{row_properties}</w:trPr>{cells}</w:tr>"


def table(headers: list[str], rows: list[list[str]], widths: list[int]) -> str:
    if sum(widths) != 9360:
        raise ValueError(f"table widths must total 9360 DXA, found {sum(widths)}")
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in widths)
    borders = (
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:left w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:right w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '</w:tblBorders>'
    )
    margins = (
        '<w:tblCellMar><w:top w:w="80" w:type="dxa"/>'
        '<w:bottom w:w="80" w:type="dxa"/>'
        '<w:start w:w="120" w:type="dxa"/><w:end w:w="120" w:type="dxa"/>'
        '</w:tblCellMar>'
    )
    properties = (
        '<w:tblPr><w:tblW w:w="9360" w:type="dxa"/>'
        '<w:tblInd w:w="120" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
        + borders
        + margins
        + '</w:tblPr>'
    )
    return (
        '<w:tbl>'
        + properties
        + f'<w:tblGrid>{grid}</w:tblGrid>'
        + _table_row(headers, widths, header=True)
        + "".join(_table_row(row, widths) for row in rows)
        + '</w:tbl>'
    )


STATUS_ROWS = [
    ["MVP implementation", "Complete locally", "All 44 A1-K4 implementation tasks have repository evidence."],
    ["Accepted fixture output", "28 / 40 / 28", "28 emails, 40 glass items, and 28 agent execution logs."],
    ["Review disposition", "8 / 20", "8 completed records and 20 human-review-required records."],
    ["Automated tests", "69 passed", "Classification, extraction, Gmail, attachments, API, tasks, storage, and imports."],
    ["Default model", "Opus", "claude-opus-4-8 is enforced by configuration checks."],
    ["Docker platform", "Healthy", "PostgreSQL, Redis, FastAPI, and Celery are running locally."],
    ["Remote CI", "Passed", "The published GitHub Actions workflow completed successfully."],
    ["MVP decision", "Accepted", "Ready for the final demo; PDF image matching is planned as a post-MVP enhancement."],
]


COMPLETED_ROWS = [
    [
        "Product acceptance review",
        "Reviewed the original assignment and every A1-K4 task as product manager and engineering owner; created a requirement-to-evidence matrix.",
    ],
    [
        "Extraction contracts",
        "Centralized glass-type required fields, preserved one record per requested item, retained type-specific output, and enforced the mirror heat-treatment exception.",
    ],
    [
        "Normalization and ambiguity",
        "Expanded decimal-inch normalization for mm, cm, meters, feet, and architectural feet-plus-inches; approximate quantity now defaults to 1 pending confirmation.",
    ],
    [
        "TT and color quality",
        "Preserved clear and low-iron values, separated spandrel type from color, retained specific grey tint, and blocked body/source/construction labels from TT output.",
    ],
    [
        "Fabrication accuracy",
        "Added structured fabrication details for holes, cutouts, notches, radii, and safety backing. Approximate or pending fabrication now routes to human review.",
    ],
    [
        "Gmail and attachments",
        "Improved visible HTML handling, conversation context, prior-message attachments, source message IDs, and read-only token behavior. TXT, CSV, TSV, DOCX, and text-layer PDF are covered.",
    ],
    [
        "Persistence and provenance",
        "Enforced SQLite foreign keys, atomic JSON export, complete internal field attribution, agent execution logs, and a separate source API/UI view.",
    ],
    [
        "API and review UI",
        "Completed dashboard metrics, filters, search, email/body/attachment detail, extracted units, missing fields, review reasons, provenance, and agent run display.",
    ],
    [
        "Docker and platform hardening",
        "Added non-root containers, localhost-only ports, shared persistent output volume, health checks, capped Celery concurrency, and a read-only Gmail credential override.",
    ],
    [
        "Live demo data",
        "Added a tested SQLite-to-PostgreSQL import and loaded the accepted 28-email dataset plus matching JSON into the running Docker platform without another LLM call.",
    ],
    [
        "CI and configuration",
        "Published and verified GitHub Actions for tests, semantic audit, UI validation, Compose validation, Gmail override validation, and Docker image build; added local configuration safety checks.",
    ],
    [
        "Documentation",
        "Completed product acceptance, A1-K4 traceability, architecture, API, deployment, platform, and final demo guidance.",
    ],
]


FINDING_ROWS = [
    [
        "Fabrication existed only in notes",
        "Holes, corner radii, safety backing, rail cutouts, and shower-door fabrication were not consistently exported as structured fields.",
        "Recovered grounded details into fabrication.details, added provenance and oracle checks, and routed approximate/pending details to review.",
    ],
    [
        "Two records were over-classified as complete",
        "RFQs 1 and 2 had approximate or pending hole/radius details but were marked completed.",
        "Moved both to human review. The accepted split changed from 10/18 to 8 completed and 20 review-required.",
    ],
    [
        "Ambiguous quantities",
        "Ranges and phrases such as roughly 15 or quantity around 20 could be interpreted as definite counts.",
        "Default quantity to 1 with default provenance and retain a review reason instead of guessing.",
    ],
    [
        "TT contamination risk",
        "Source labels such as body and construction labels such as monolithic or IGU could enter TT fields.",
        "Added deterministic cleanup and audit rules; no body nonsense is present in accepted JSON.",
    ],
    [
        "Destructive replacement timing",
        "replace-existing could clear stored output before input and model validation completed.",
        "Deferred replacement until a valid extraction run actually begins.",
    ],
    [
        "Docker demo showed one email",
        "The platform database contained only the earlier smoke-test record.",
        "Imported all accepted records, items, provenance, and run logs into PostgreSQL and synchronized the shared JSON volume.",
    ],
]


VALIDATION_ROWS = [
    ["Project configuration", "Passed", "Opus default, canonical paths, secret ignores, workflow trigger, Compose safety, and non-root image checks."],
    ["Automated test suite", "Passed", "69 tests completed successfully."],
    ["Semantic fixture oracle", "Passed", "Every supplied fixture email and all 40 expected items matched the checked-in acceptance result."],
    ["JSON and SQLite audit", "Passed", "28 emails, 40 items, 28 runs; completion/review state, source integrity, and database integrity matched."],
    ["UI route validation", "Passed", "All 28 summaries, filters, review states, source endpoint, and a complex mixed-package detail page rendered correctly."],
    ["Docker configurations", "Passed", "Base Compose and Gmail credential override both validated."],
    ["Docker image build", "Passed", "Clean Python 3.12 image build completed without compiler packages in the runtime image."],
    ["Live PostgreSQL", "Passed", "Running API reports 28 emails, 40 items, and 28 agent runs."],
    ["Live Redis and Celery", "Passed", "Redis returned PONG and one Celery worker node returned pong at concurrency 2."],
    ["Container security and storage", "Passed", "API and worker run as uid/gid 999(app) and share a writable persistent output volume."],
    ["GitHub Actions", "Passed", "The published test/audit and Docker workflow completed successfully in GitHub."],
    ["Dependency and diff checks", "Passed", "pip check found no broken requirements and git diff --check found no whitespace errors."],
]


REQUIREMENT_ROWS = [
    ["A", "A1-A4", "Verified", "Glass fields, required/optional matrix, human review rules, and future agent direction."],
    ["B", "B1-B4", "Verified", "Multi-agent workflow, BaseAgent/registry, LangGraph, state, and contracts."],
    ["C", "C1-C5", "Verified live", "FastAPI, PostgreSQL, Redis, Celery, and Docker Compose."],
    ["D", "D1-D2", "Verified for MVP", "Gmail/thread email extraction and supported text-based attachments."],
    ["E", "E1-E7", "Verified", "All four glass makeups, attachment framework, quality improvements, and acceptance oracle."],
    ["F", "F1-F3", "Verified", "Emails, per-item units, internal provenance, and agent execution logs."],
    ["G", "G1-G5", "Verified automatically", "Opening dashboard, email/attachment detail, results, filters, responsive behavior, and validation fixes."],
    ["H", "H1-H5", "Verified", "Classification, extraction, API, Celery, persistence, Gmail, attachment, and final QA tests."],
    ["I", "I1-I4", "Verified remotely", "GitHub Actions and the automated test/audit and Docker pipeline completed successfully."],
    ["J", "J1", "Verified locally", "Final QA and live Docker pass; fresh paid Opus rerun requires external-transmission approval."],
    ["K", "K1-K4", "Verified", "Architecture, API, deployment, acceptance, traceability, and final demo documentation."],
]


BOUNDARY_ROWS = [
    [
        "Fresh full Opus rerun",
        "External confirmation",
        "Requires explicit authorization to transmit the synthetic fixture text to Anthropic and consume API credits.",
    ],
    [
        "PDF image matching",
        "Planned post-MVP enhancement",
        "Render PDF pages and associate drawings or images with the corresponding extracted glass item using page provenance, confidence thresholds, and human-review routing.",
    ],
    [
        "Human visual inspection",
        "Recommended delivery check",
        "Automated UI validation passes; perform a short desktop and mobile visual review before presentation.",
    ],
    [
        "Live Gmail mailbox",
        "Environment-dependent",
        "OAuth ingestion is covered by tests; a live smoke test depends on access to the intended mailbox and token.",
    ],
    [
        "Image-only OCR",
        "Optional stretch scope",
        "Photographs, scans, and handwritten takeoffs remain outside the stated MVP scope.",
    ],
    [
        "Production security",
        "Out of demo scope",
        "The localhost API and demo database credentials require authentication, managed secrets, TLS, backups, and monitoring before production use.",
    ],
]


DELIVERABLE_ROWS = [
    ["Acceptance decision", "docs/product_acceptance.md", "MVP decision, policy resolutions, improvements, and external confirmations."],
    ["Requirement matrix", "docs/requirement_traceability.md", "Task-by-task A1-K4 status and evidence."],
    ["Demo guide", "docs/final_demo.md", "Extraction, audit, UI, platform import, and Docker walkthrough."],
    ["Accepted JSON", "outputs/rfq_extractions.json", "28 clean email records containing 40 per-item glass results."],
    ["Accepted SQLite", "outputs/rfq_extractions.db", "Emails, items, field provenance, and 28 agent execution logs."],
    ["Acceptance oracle", "tests/fixtures/expected_fixture_extractions.json", "Expected result for every supplied email and item."],
    ["QA command", "scripts/final_qa.py --docker-build", "Tests, compile, configuration, semantic audit, UI, Compose, and image build."],
    ["Live dashboard", "http://127.0.0.1:8000/view", "Running Docker/PostgreSQL review interface populated with accepted data."],
]


NEXT_ROWS = [
    ["1", "Complete visual demo check", "Review dashboard and detail pages at desktop and mobile widths."],
    ["2", "Design PDF image matching", "Define how PDF drawings and images map to extracted glass items, including page-level provenance and review thresholds."],
    ["3", "Build matching fixtures and evaluation", "Create representative PDF fixtures and measure correct matches, unmatched images, confidence, and human-review behavior."],
    ["4", "Run fresh Opus extraction if approved", "Regenerate all fixtures only after external transmission and API-credit use are authorized."],
    ["5", "Optional mailbox/OCR follow-up", "Run a live Gmail smoke test when credentials are available; keep general image OCR as separate stretch scope."],
]


def document_xml() -> str:
    body: list[str] = []
    body.append(para("WEEKLY STATUS REPORT", style="Title", after=80, keep_next=True))
    body.append(
        para(
            "Glass RFQ Extraction System - Final Product Acceptance and MVP Readiness",
            style="Subtitle",
            after=220,
        )
    )
    body.append(label_para("Prepared for", "Bilvantis Internship Project"))
    body.append(label_para("Prepared by", "Srikar Devesetti"))
    body.append(label_para("Report date", "August 12, 2026"))
    body.append(label_para("Reporting window", "August 7-12, 2026"))
    body.append(
        label_para(
            "Current phase",
            "MVP accepted and GitHub Actions verified; final demo and enhancement planning",
        )
    )
    body.append(
        callout(
            "Executive Summary",
            "The Glass RFQ Extraction System completed a product-manager-led final acceptance review against the original assignment and all 44 A1-K4 tasks. All mandatory implementation work is complete. The accepted artifacts contain 28 emails, 40 per-item glass records, and 28 agent execution logs with claude-opus-4-8 recorded as the model. Sixty-nine tests, the full semantic fixture oracle, JSON/SQLite integrity checks, UI validation, both Docker Compose configurations, a clean image build, the live PostgreSQL/Redis/Celery/FastAPI platform, and the published GitHub Actions workflow all pass. The final disposition is 8 completed records and 20 human-review-required records; two additional RFQs were intentionally moved to review after approximate or pending hole/radius fabrication was identified. PDF image-to-item matching is planned as a post-MVP enhancement and is not a blocker for the accepted assignment scope.",
        )
    )

    body.append(para("Status Snapshot", style="Heading1", keep_next=True))
    body.append(table(["Measure", "Current State", "Evidence"], STATUS_ROWS, [2100, 1900, 5360]))

    body.append(para("Work Completed This Period", style="Heading1", keep_next=True))
    body.append(table(["Area", "Completed Work"], COMPLETED_ROWS, [2500, 6860]))

    body.append(para("Acceptance Findings and Corrections", style="Heading1", keep_next=True))
    body.append(
        table(
            ["Finding", "Observed Risk", "Correction / Result"],
            FINDING_ROWS,
            [2100, 3300, 3960],
        )
    )

    body.append(para("Validation Evidence", style="Heading1", keep_next=True))
    body.append(table(["Check", "Result", "Evidence"], VALIDATION_ROWS, [2300, 1200, 5860]))

    body.append(para("Requirement Status by Workstream", style="Heading1", keep_next=True))
    body.append(
        table(
            ["Section", "Task IDs", "Status", "Acceptance Evidence"],
            REQUIREMENT_ROWS,
            [1000, 1100, 1900, 5360],
        )
    )
    body.append(
        callout(
            "Requirement conclusion",
            "No mandatory implementation task remains open. The GitHub Actions workflow has completed successfully, closing the remaining DevOps confirmation. PDF image matching is recorded as planned post-MVP work rather than an unmet assignment requirement. The complete task-level evidence is recorded in docs/requirement_traceability.md.",
        )
    )

    body.append(para("Known Boundaries and Planned Enhancements", style="Heading1", keep_next=True))
    body.append(
        table(
            ["Item", "Classification", "Required Handling"],
            BOUNDARY_ROWS,
            [2200, 2100, 5060],
        )
    )

    body.append(para("Key Deliverables", style="Heading1", keep_next=True))
    body.append(table(["Deliverable", "Location", "Purpose"], DELIVERABLE_ROWS, [2100, 3300, 3960]))

    body.append(para("Next Actions", style="Heading1", keep_next=True))
    body.append(table(["#", "Action", "Outcome"], NEXT_ROWS, [600, 2700, 6060]))

    body.append(para("Overall Assessment", style="Heading1", keep_next=True))
    body.append(
        callout(
            "MVP accepted and CI verified",
            "The project is ready for final demonstration as an internship MVP. Extraction quality, human-review behavior, structured output, persistence, agent logging, API/UI access, asynchronous execution, Docker deployment, documentation, and remote CI are implemented and verified. The current platform is a localhost demonstration environment rather than a production service. Final delivery should focus on the brief human visual review. PDF image-to-item matching can proceed as the next post-MVP enhancement, while a fresh Opus run or live Gmail validation should be performed only when the corresponding external access and data-transmission approvals are available.",
        )
    )

    section = (
        '<w:sectPr>'
        '<w:headerReference w:type="default" r:id="rId1"/>'
        '<w:footerReference w:type="default" r:id="rId2"/>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" '
        'w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        '<w:cols w:space="720"/><w:docGrid w:linePitch="360"/>'
        '</w:sectPr>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{NS}" xmlns:r="{R_NS}"><w:body>'
        + "".join(body)
        + section
        + "</w:body></w:document>"
    )


def content_types_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
</Types>'''


def document_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>'''


def header_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="{NS}">
  <w:p>
    <w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="left"/></w:pPr>
    <w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="18"/><w:color w:val="667085"/></w:rPr><w:t>Glass RFQ Extraction System | Weekly Status Report</w:t></w:r>
  </w:p>
</w:hdr>'''


def footer_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="{NS}">
  <w:p>
    <w:pPr><w:spacing w:before="0" w:after="0"/><w:jc w:val="right"/></w:pPr>
    <w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="18"/><w:color w:val="667085"/></w:rPr><w:t xml:space="preserve">Page </w:t></w:r>
    <w:fldSimple w:instr=" PAGE "><w:r><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="18"/><w:color w:val="667085"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple>
  </w:p>
</w:ftr>'''


def build_docx(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types_xml())
        docx.writestr("_rels/.rels", rels_xml())
        docx.writestr("word/_rels/document.xml.rels", document_rels_xml())
        docx.writestr("word/document.xml", document_xml())
        docx.writestr("word/styles.xml", styles_xml())
        docx.writestr("word/settings.xml", settings_xml())
        docx.writestr("word/header1.xml", header_xml())
        docx.writestr("word/footer1.xml", footer_xml())


if __name__ == "__main__":
    build_docx(OUT_PATH)
    print(OUT_PATH)
