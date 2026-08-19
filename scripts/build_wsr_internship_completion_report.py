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


OUT_PATH = Path("reports/WSR_RFQ_Extraction_Status_Report_2026-08-19.docx")


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
    ["Assignment scope", "44 / 44 verified", "Every scheduled A1-K4 task has implementation and acceptance evidence."],
    ["Fresh Opus acceptance", "28 / 40 / 28", "28 emails, 40 per-item glass records, and 28 agent execution logs."],
    ["Review disposition", "8 / 20", "8 completed emails and 20 correctly routed to human review."],
    ["Image-only PDF run", "3 / 4", "Three OCR email fixtures produced four items; two emails completed and one required review."],
    ["Automated tests", "81 passed", "Classification, extraction, OCR, Gmail, API, UI, Celery, storage, and sender coverage."],
    ["Default model", "Opus", "claude-opus-4-8 is configured, reported by the API, and recorded on fresh results."],
    ["Platform and CI", "Healthy / passed", "Docker services are healthy and the published GitHub Actions workflow passes."],
    ["Final decision", "Handoff ready", "The internship MVP is complete, validated, documented, and ready for demonstration."],
]


COMPLETED_ROWS = [
    [
        "Fresh full Opus extraction",
        "Ran all 28 synthetic RFQ emails through claude-opus-4-8 with explicit authorization, retained separate dated artifacts, and promoted only the audited result.",
    ],
    [
        "Model-drift hardening",
        "The first strict audit exposed seven wording/normalization differences. Added reusable rules for approx, seamed edges, color-tint wording, rectangular door lites, pull holes, and inferred item marks.",
    ],
    [
        "Image-only OCR pipeline",
        "Added local PDF page rendering and Tesseract OCR for textless PDFs and PNG/JPEG/TIFF/WebP images, with measured confidence, page metadata, and deterministic review routing.",
    ],
    [
        "Realistic PDF fixtures",
        "Generated three raster-only RFQ PDFs covering monolithic, insulated, and intentionally incomplete laminated glass; created matching local email fixtures with attachment directives.",
    ],
    [
        "Attachment-aware email sender",
        "Extended the Gmail sample sender to parse local attachment directives, validate fixture paths, and create MIME messages containing the generated PDF files.",
    ],
    [
        "Extraction and provenance",
        "The OCR Opus run produced four correct items. Every OCR field is attributed internally to attachment:<filename>; exported glass units remain clean with no body/source labels in TT or specification values.",
    ],
    [
        "Human-review controls",
        "OCR failure or low confidence triggers review, OCR-based confidence caps extracted field scores, and the incomplete laminated fixture correctly leaves HT2 null instead of guessing.",
    ],
    [
        "Review UI improvements",
        "Added attachment extraction method, OCR confidence, preview/error details, and responsive rendering. Desktop and mobile visual checks found no page overflow, overlap, or browser console errors.",
    ],
    [
        "Docker and CI OCR support",
        "Installed Tesseract in API/worker images and CI, rebuilt the platform, and confirmed OCR inside Docker at 93-94% confidence for all three generated PDFs.",
    ],
    [
        "Live platform update",
        "Loaded the audited fresh Opus dataset into canonical JSON/SQLite and PostgreSQL; the running API reports 28 emails, 40 items, 28 runs, and claude-opus-4-8.",
    ],
    [
        "Gmail and interface checks",
        "Read-only Gmail OAuth refresh/authentication passed; the current 30-day RFQ query returned no matching message. Human UI checks passed at 1440x1000 and 390x844.",
    ],
    [
        "Final documentation",
        "Updated product acceptance, A1-K4 traceability, architecture, API, deployment, final demo, OCR limitations, and internship handoff guidance.",
    ],
]


FINDING_ROWS = [
    [
        "Opus wording varied",
        "Accurate facts used variants such as seamed, grey tinted, and approx, which did not satisfy the strict acceptance vocabulary.",
        "Added deterministic canonicalization and five regression tests; the replayed fresh response passed all 40 expected items.",
    ],
    [
        "Approximate radius was completed",
        "The abbreviation approx was not included in the fabrication-review pattern, so one RFQ was initially over-classified.",
        "Expanded the deterministic pattern and restored the accepted 8 completed / 20 review-required disposition.",
    ],
    [
        "Door-lite shape and labels drifted",
        "An item with pending dimensions became square and two shower items omitted the fixed panel and door marks.",
        "Recovered rectangular context and specific leading-note labels without adding unsupported values.",
    ],
    [
        "Attachment confidence needed control",
        "An LLM confidence value could otherwise exceed confidence measured from the OCR source.",
        "Cap OCR-sourced fields at measured OCR confidence and force review below the configured 90% threshold.",
    ],
    [
        "PDFs were not viewable inline",
        "The review UI displays attachment metadata and OCR text, but it does not serve or embed the original PDF page.",
        "Recorded a secure View PDF/download endpoint and inline viewer as a post-internship enhancement, not an MVP blocker.",
    ],
    [
        "No live RFQ was available",
        "Gmail OAuth succeeded, but the configured 30-day query found zero matching messages for a body/attachment extraction smoke.",
        "Documented the environment result; fixture and mocked Gmail coverage remain passing without inventing live evidence.",
    ],
]


VALIDATION_ROWS = [
    ["Fresh full Opus run", "Passed", "28 emails, 40 items, 28 logs; the normalized result matches every checked-in expected item."],
    ["Image-PDF Opus run", "Passed", "Three image-only emails produced four items with the intended 2 completed / 1 review disposition."],
    ["OCR ground truth", "Passed", "Marks, dimensions, quantities, lite makeup, fabrication, missing HT2, and attachment provenance matched the generated PDFs."],
    ["Automated test suite", "Passed", "81 tests completed successfully, including real-Tesseract PDF fixtures and failure/low-confidence paths."],
    ["Final QA gate", "Passed", "Configuration, compile, tests, semantic audit, UI validation, Compose, and Gmail override checks passed."],
    ["Canonical persistence", "Passed", "JSON and SQLite match at 28 emails, 40 items, and 28 runs with valid foreign keys and source integrity."],
    ["Live PostgreSQL API", "Passed", "The rebuilt API reports the accepted counts and claude-opus-4-8 as the configured model."],
    ["Redis and Celery", "Passed", "Redis returned PONG and the rebuilt Celery worker returned pong."],
    ["Docker OCR", "Passed", "Tesseract 5.5 is present in API and worker; all three PDFs OCR at approximately 93-94%."],
    ["Desktop UI", "Passed", "1440x1000 dashboard/detail checks showed readable sections, working filters, and no horizontal page overflow."],
    ["Mobile UI", "Passed", "390x844 checks showed stacked filters/metrics, internal table scrolling, and no overlap."],
    ["GitHub Actions", "Passed", "The published automated test/audit and Docker build workflow completed successfully."],
    ["Gmail OAuth", "Passed with no match", "Read-only authentication succeeded; the 30-day RFQ query returned zero messages."],
    ["Dependency and diff checks", "Passed", "pip check reported no broken dependencies and git diff --check found no whitespace errors."],
]


REQUIREMENT_ROWS = [
    ["A", "A1-A4", "Verified", "Glass fields, required/optional matrix, human review rules, and future agent direction."],
    ["B", "B1-B4", "Verified", "Multi-agent workflow, BaseAgent/registry, LangGraph, state, and contracts."],
    ["C", "C1-C5", "Verified live", "FastAPI, PostgreSQL, Redis, Celery, and Docker Compose."],
    ["D", "D1-D2", "Verified plus OCR", "Gmail/thread extraction, text attachments, and typed image-only PDF/raster OCR."],
    ["E", "E1-E7", "Verified plus OCR", "All four glass makeups, attachment framework, image fixtures, quality rules, and fresh Opus oracle."],
    ["F", "F1-F3", "Verified", "Emails, per-item units, internal provenance, and agent execution logs."],
    ["G", "G1-G5", "Verified", "Dashboard, email/attachment detail, results, filters, automated checks, and human desktop/mobile validation."],
    ["H", "H1-H5", "Verified", "81 tests covering classification, extraction, OCR, API, Celery, persistence, Gmail, sender, and final QA."],
    ["I", "I1-I4", "Verified remotely", "GitHub Actions and the automated test/audit and Docker pipeline completed successfully."],
    ["J", "J1", "Verified", "Fresh Opus, image-PDF extraction, final QA, live Docker, UI, and Gmail OAuth checks completed."],
    ["K", "K1-K4", "Verified", "Architecture, API, deployment, acceptance, traceability, demo, and final handoff documentation."],
]


BOUNDARY_ROWS = [
    [
        "Inline PDF display",
        "Post-internship enhancement",
        "Add authenticated attachment storage/serving plus a View PDF action and inline viewer; the current UI shows OCR text and metadata.",
    ],
    [
        "Drawing-to-item matching",
        "Post-internship enhancement",
        "Associate drawing regions or images with extracted glass items using page/region provenance, confidence thresholds, and review routing.",
    ],
    [
        "Difficult scan coverage",
        "Optional stretch scope",
        "Add rotated, skewed, noisy, low-resolution, and mixed multi-page fixtures with preprocessing and confidence evaluation.",
    ],
    [
        "Handwriting and technical drawings",
        "Optional stretch scope",
        "General handwriting and drawing-aware interpretation need dedicated evaluation to avoid confusing rough openings with cut sizes.",
    ],
    [
        "Live Gmail content smoke",
        "Environment-dependent",
        "Repeat with a known test RFQ when the mailbox contains one; read-only authentication is already confirmed.",
    ],
    [
        "Production security",
        "Out of demo scope",
        "Add application authentication, managed secrets, TLS, least-privilege database accounts, backups, audit retention, and monitoring.",
    ],
]


DELIVERABLE_ROWS = [
    ["Acceptance decision", "docs/product_acceptance.md", "Final MVP decision, policy resolutions, fresh Opus evidence, and optional boundaries."],
    ["Requirement matrix", "docs/requirement_traceability.md", "Task-by-task A1-K4 status and evidence."],
    ["Demo guide", "docs/final_demo.md", "Authorized extraction, audit, OCR fixture, UI, PostgreSQL, Celery, and Docker walkthrough."],
    ["Accepted JSON", "outputs/rfq_extractions.json", "Fresh audited Opus output: 28 email records containing 40 per-item results."],
    ["Accepted SQLite", "outputs/rfq_extractions.db", "Emails, items, internal field provenance, and 28 agent execution logs."],
    ["Image email fixtures", "fixtures/image_pdf_rfq_emails.txt", "Three local synthetic emails referencing raster-only PDF attachments."],
    ["Image PDF fixtures", "fixtures/attachments/image_rfq_*.pdf", "Monolithic, insulated, and laminated-review quote schedules."],
    ["OCR implementation", "agent_rfq_extractor/attachment_extraction.py", "Native text extraction, local OCR, confidence, limits, and review metadata."],
    ["Acceptance oracle", "tests/fixtures/expected_fixture_extractions.json", "Expected result for every supplied email and item."],
    ["QA command", "scripts/final_qa.py --docker-build", "Tests, compile, configuration, semantic audit, UI, Compose, and image build."],
    ["Live dashboard", "http://127.0.0.1:8000/view", "Running Docker/PostgreSQL review interface populated with accepted data."],
]


HANDOFF_ROWS = [
    ["Application", "Ready", "Docker dashboard is available at http://127.0.0.1:8000/view with the accepted PostgreSQL dataset."],
    ["Acceptance evidence", "Ready", "Product acceptance, requirement traceability, final demo instructions, canonical outputs, and the 40-item oracle are present."],
    ["OCR demonstration", "Ready", "Three raster-only PDF quotes, local email fixtures, actual Opus results, and real-Tesseract tests demonstrate image-only extraction."],
    ["Operational reproduction", "Ready", "README and deployment/demo guides contain local, Docker, audit, import, UI, and worker validation commands."],
    ["Source control", "Final action", "Review the working tree, commit the final implementation and report, push the branch, and confirm the last GitHub Actions run."],
    ["Production ownership", "Future decision", "Assign ownership for authentication, managed secrets, migrations, monitoring, backup/retention, and advanced document evaluation."],
]


NEXT_ROWS = [
    ["1", "Final demonstration", "Use docs/final_demo.md to show accepted extraction, review routing, provenance, OCR, and the Docker dashboard."],
    ["2", "Repository handoff", "Commit the reviewed source, fixtures, canonical outputs, tests, and documentation; confirm the final GitHub Actions run."],
    ["3", "Add secure PDF viewing", "Persist approved attachment binaries or references and expose an authenticated view/download endpoint."],
    ["4", "Expand OCR evaluation", "Add rotated, noisy, low-resolution, mixed multi-page, handwriting, and drawing fixtures with measurable acceptance thresholds."],
    ["5", "Production readiness review", "Define authentication, secrets, database migration, backups, observability, retention, and operational ownership."],
]


def document_xml() -> str:
    body: list[str] = []
    body.append(para("WEEKLY STATUS REPORT", style="Title", after=80, keep_next=True))
    body.append(
        para(
            "Glass RFQ Extraction System - Final Internship Week and Project Handoff",
            style="Subtitle",
            after=220,
        )
    )
    body.append(label_para("Prepared for", "Bilvantis Internship Project"))
    body.append(label_para("Prepared by", "Srikar Devesetti"))
    body.append(label_para("Report date", "August 19, 2026"))
    body.append(label_para("Reporting window", "August 13-19, 2026"))
    body.append(
        label_para(
            "Current phase",
            "Final internship week; MVP accepted, validated, and ready for handoff",
        )
    )
    body.append(
        callout(
            "Executive Summary",
            "During the final internship week, the Glass RFQ Extraction System completed its remaining external and stretch validation. With explicit authorization, all 28 provided RFQ emails were extracted again using claude-opus-4-8. The accepted artifacts contain 40 per-item glass records and 28 execution logs, with 8 completed emails and 20 correctly routed to human review. The first strict audit exposed seven normal model wording differences; reusable deterministic rules and five regression tests were added, after which the fresh result passed the complete 28-email/40-item oracle. Typed image-only PDF and raster OCR was also implemented using local Tesseract, validated with three realistic PDF quote emails and four extracted items. Eighty-one tests, final QA, desktop/mobile review, read-only Gmail OAuth, Docker OCR, PostgreSQL, Redis, Celery, FastAPI, and GitHub Actions all pass. All 44 A1-K4 tasks are verified, the MVP is ready for final demonstration and handoff, and only optional production or advanced-document enhancements remain.",
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
            "No mandatory implementation or validation task remains open. The fresh Opus extraction, image-only PDF run, human visual pass, Gmail OAuth check, Docker rebuild, and final QA are complete. Secure inline PDF display, difficult-scan evaluation, handwriting, and drawing-to-item matching are recorded as post-internship enhancements rather than unmet assignment requirements. Full task-level evidence is maintained in docs/requirement_traceability.md.",
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

    body.append(para("Internship Closeout and Handoff", style="Heading1", keep_next=True))
    body.append(table(["Handoff Item", "State", "Handoff Note"], HANDOFF_ROWS, [2200, 1500, 5660]))

    body.append(para("Next Actions", style="Heading1", keep_next=True))
    body.append(table(["#", "Action", "Outcome"], NEXT_ROWS, [600, 2700, 6060]))

    body.append(para("Overall Assessment", style="Heading1", keep_next=True))
    body.append(
        callout(
            "Internship MVP complete and handoff ready",
            "The project now demonstrates the complete internship assignment: reliable per-item glass RFQ extraction, deterministic normalization, construction-specific completeness rules, human-review routing, auditable JSON/SQLite/PostgreSQL persistence, source attribution, agent execution logs, API/UI access, Celery execution, Docker deployment, CI, and final documentation. The final week also delivered a meaningful stretch capability for typed image-only PDF OCR without weakening the no-guess policy. The running system remains a localhost demonstration rather than a production service, but the repository contains the evidence, fixtures, commands, and handoff documentation needed for another engineer to reproduce the demo and continue development. Recommended future work is clearly isolated from the accepted MVP so project completion is not overstated or obscured.",
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
