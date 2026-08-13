from __future__ import annotations

import html
import zipfile
from pathlib import Path


OUT_PATH = Path("reports/WSR_RFQ_Feature_Status_Report_2026-07-17.docx")

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def w_attr(name: str, value: object) -> str:
    return f'w:{name}="{esc(value)}"'


def color(hex_value: str) -> str:
    return hex_value.replace("#", "")


def run(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    size: int | None = None,
    color_hex: str | None = None,
) -> str:
    props: list[str] = ['<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>']
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if size is not None:
        props.append(f'<w:sz {w_attr("val", size * 2)}/>')
    if color_hex:
        props.append(f'<w:color {w_attr("val", color(color_hex))}/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>"
    space = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    return f"<w:r>{rpr}<w:t{space}>{esc(text)}</w:t></w:r>"


def para(
    text: str = "",
    *,
    style: str | None = None,
    before: int | None = None,
    after: int | None = None,
    bold: bool = False,
    italic: bool = False,
    size: int | None = None,
    color_hex: str | None = None,
    keep_next: bool = False,
) -> str:
    ppr: list[str] = []
    if style:
        ppr.append(f'<w:pStyle {w_attr("val", style)}/>')
    if keep_next:
        ppr.append("<w:keepNext/>")
    if before is not None or after is not None:
        ppr.append(
            f'<w:spacing {w_attr("before", before or 0)} {w_attr("after", after or 0)} '
            'w:line="264" w:lineRule="auto"/>'
        )
    ppr_xml = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
    return (
        f"<w:p>{ppr_xml}"
        + (run(text, bold=bold, italic=italic, size=size, color_hex=color_hex) if text else "")
        + "</w:p>"
    )


def label_para(label: str, value: str) -> str:
    return (
        '<w:p><w:pPr><w:spacing w:before="0" w:after="40" w:line="264" '
        'w:lineRule="auto"/></w:pPr>'
        + run(label + ": ", bold=True)
        + run(value)
        + "</w:p>"
    )


def cell(
    text: str,
    width: int,
    *,
    fill: str | None = None,
    bold: bool = False,
    shade_text: str | None = None,
    size: int = 9,
) -> str:
    shd = f'<w:shd w:fill="{color(fill)}"/>' if fill else ""
    tcpr = (
        f'<w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shd}'
        '<w:vAlign w:val="center"/></w:tcPr>'
    )
    paragraphs = []
    for part in str(text).split("\n"):
        paragraphs.append(
            '<w:p><w:pPr><w:spacing w:before="0" w:after="50" w:line="260" '
            'w:lineRule="auto"/></w:pPr>'
            + run(part, bold=bold, size=size, color_hex=shade_text)
            + "</w:p>"
        )
    return f"<w:tc>{tcpr}{''.join(paragraphs)}</w:tc>"


def row(values: list[str], widths: list[int], *, header: bool = False) -> str:
    trpr = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
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
        for value, width in zip(values, widths)
    )
    return f"<w:tr>{trpr}{cells}</w:tr>"


def table(headers: list[str], rows: list[list[str]], widths: list[int]) -> str:
    grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in widths)
    borders = (
        '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:left w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:right w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="D0D5DD"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="D0D5DD"/></w:tblBorders>'
    )
    margins = (
        '<w:tblCellMar><w:top w:w="80" w:type="dxa"/>'
        '<w:bottom w:w="80" w:type="dxa"/>'
        '<w:start w:w="120" w:type="dxa"/><w:end w:w="120" w:type="dxa"/>'
        "</w:tblCellMar>"
    )
    pr = (
        '<w:tblPr><w:tblW w:w="9360" w:type="dxa"/>'
        '<w:tblInd w:w="120" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
        + borders
        + margins
        + "</w:tblPr>"
    )
    return (
        "<w:tbl>"
        + pr
        + f"<w:tblGrid>{grid}</w:tblGrid>"
        + row(headers, widths, header=True)
        + "".join(row(item, widths) for item in rows)
        + "</w:tbl>"
    )


def callout(title: str, body: str) -> str:
    tcpr = '<w:tcPr><w:tcW w:w="9360" w:type="dxa"/><w:shd w:fill="F4F6F9"/></w:tcPr>'
    p1 = (
        '<w:p><w:pPr><w:spacing w:after="80"/></w:pPr>'
        + run(title, bold=True, color_hex="#1F3A5F")
        + "</w:p>"
    )
    p2 = (
        '<w:p><w:pPr><w:spacing w:after="0" w:line="264" w:lineRule="auto"/></w:pPr>'
        + run(body)
        + "</w:p>"
    )
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/>'
        '<w:tblInd w:w="120" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
        '<w:tblBorders><w:top w:val="single" w:sz="6" w:color="B8C7D9"/>'
        '<w:left w:val="single" w:sz="6" w:color="B8C7D9"/>'
        '<w:bottom w:val="single" w:sz="6" w:color="B8C7D9"/>'
        '<w:right w:val="single" w:sz="6" w:color="B8C7D9"/></w:tblBorders>'
        '<w:tblCellMar><w:top w:w="140" w:type="dxa"/>'
        '<w:bottom w:w="140" w:type="dxa"/><w:start w:w="180" w:type="dxa"/>'
        '<w:end w:w="180" w:type="dxa"/></w:tblCellMar></w:tblPr>'
        '<w:tblGrid><w:gridCol w:w="9360"/></w:tblGrid><w:tr>'
        f"<w:tc>{tcpr}{p1}{p2}</w:tc></w:tr></w:tbl>"
    )


DONE = [
    ("A1", "Requirements", "Glass type analysis and field identification", "Type aliases, field parsing, and grouped JSON output are implemented."),
    ("A2", "Requirements", "Define mandatory vs optional fields by glass type", "Required field rules are enforced by monolithic, laminated, insulated, and laminated-insulated type."),
    ("A3", "Requirements", "Define Human Review business rules", "Missing required fields, ambiguous requests, no-item cases, and conflicts trigger review."),
    ("A4", "Requirements", "Define future agent architecture", "ExtractorAgent is implemented as Agent 1 behind a reusable agent interface."),
    ("B1", "Architecture", "Multi-Agent Framework Design", "AgentWorkflow supports ordered agent steps, context, output handoff, and stop rules."),
    ("B2", "Architecture", "Agent Base Class & Registry Design", "BaseAgent, AgentContext, AgentResult, AgentRegistry, and ExtractorAgent are implemented."),
    ("B3", "Architecture", "LangGraph Orchestrator Setup", "LangGraph extraction flow runs prepare, extract, normalize, review, and assemble."),
    ("B4", "Architecture", "State Management & Agent Contracts", "Agent result/context contracts are defined and execution logs consume AgentResult objects."),
    ("C1", "Infrastructure", "FastAPI Project Setup", "API exposes health, stored emails, agent runs, sync extraction, queued extraction, and HTML view endpoints."),
    ("C2", "Infrastructure", "PostgreSQL Setup & Schema Design", "PostgreSQL schema mirrors SQLite tables for emails, items, and agent_runs."),
    ("C3", "Infrastructure", "Redis Setup", "Redis is configured as Celery broker and result backend."),
    ("C4", "Infrastructure", "Celery Queue Framework Setup", "Celery app and fixture/Gmail extraction tasks are wired to RFQPipeline."),
    ("C5", "Infrastructure", "Docker Compose Setup", "Compose starts PostgreSQL, Redis, API, and worker; validated end-to-end."),
    ("D1", "Extraction from mailbox", "Email data extraction", "Gmail/body extraction path, fixture path, and thread-aware metadata are implemented."),
    ("E1", "Extractor Agent", "Email Classification Logic", "Glass type detection covers monolithic, laminated, insulated, and laminated-insulated."),
    ("E2", "Extractor Agent", "Monolithic Extraction Logic", "Dimensions, TK, HT, TT/color, fabrication, shape, quantity, and review rules are implemented."),
    ("E3", "Extractor Agent", "Laminated Extraction Logic", "Per-lite TK/HT/TT and interlayer material/thickness extraction are implemented."),
    ("E4", "Extractor Agent", "Insulated Extraction Logic", "Per-lite fields, spacer, gas fill, Low-E context, and missing-field rules are implemented."),
    ("E5", "Extractor Agent", "Laminated-Insulated Extraction Logic", "Three-lite extraction, laminated_lite, spacer, interlayer, and no-inheritance guards are implemented."),
    ("F1", "Database Layer", "Store Emails", "Emails table stores message metadata, status, body, review JSON, attachments JSON, model, and raw JSON."),
    ("F2", "Database Layer", "Store Extracted Units", "Items table stores searchable fields plus type-specific spec_json and raw_json."),
    ("F3", "Database Layer", "Store Agent Execution Logs", "agent_runs stores agent name, status, model, timing, email id, error, review status, item count, and metadata."),
    ("G3", "UI", "Extraction Results View", "Lightweight FastAPI HTML view renders extraction summaries and per-email extraction details."),
    ("H1", "Testing", "Unit Tests - Classification Logic", "Fixture/classification tests cover glass grouping and correction-oriented examples."),
    ("H2", "Testing", "Unit Tests - Extraction Logic", "Fixture extraction tests cover monolithic, mixed packages, area-only review, IGU color, and LIU heat treatment."),
    ("H3", "Testing", "API Tests", "API tests cover read endpoints, missing resources, queued endpoint shape, and HTML view rendering."),
    ("K4", "Demo", "End to end demo preparation", "docs/final_demo.md documents extraction, audit, API view, and Docker validation demo steps."),
]


PARTIAL = [
    ("D2", "Extraction from mailbox", "Attachment data extraction", "Text/text-layer attachments are supported; image-only/OCR attachments remain out of scope and need more real attachment testing."),
    ("E6", "Extractor Agent", "Attachment Processing Framework", "Basic text attachment support exists; richer attachment workflows and OCR are not implemented."),
    ("E7", "Extractor Agent", "Testing and Improvements", "31 tests plus audit script exist; broader real-world regression coverage can still be added."),
    ("G1", "UI", "Main opening page", "The /view route works as a simple opening results page, but it is not a polished product UI."),
    ("G2", "UI", "Email & Attachments Display", "Stored email records are visible; attachment display is not yet a full UI feature."),
    ("G4", "UI", "Validation of UI", "HTML rendering is API-tested and smoke-tested, but no browser screenshot QA suite exists."),
    ("H4", "Testing", "Celery Worker Tests", "Docker/Celery smoke test passed; dedicated worker unit/integration tests are still light."),
    ("H5", "Testing", "Testing and Improvements", "Core test suite passes, but more fixture emails and edge cases should be locked down."),
    ("I3", "DevOps", "Docker Build Pipeline", "Docker Compose was validated locally; CI-based Docker build pipeline is not present."),
    ("K1", "Documentation", "Architecture Documentation", "README and multi-agent docs exist; final architecture document still needs polish."),
    ("K2", "Documentation", "API Documentation", "docs/api.md exists and includes /view; final API documentation can be expanded."),
    ("K3", "Documentation", "Deployment Guide", "docs/platform.md exists; full deployment guide with operational notes is not final."),
]


NOT_DONE = [
    ("G5", "UI", "Fix the validation findings", "Formal UI validation findings have not been produced yet."),
    ("I1", "DevOps", "GitHub Actions CI Setup", "No GitHub Actions workflow has been added."),
    ("I2", "DevOps", "Automated Test Pipeline", "Tests run locally; automated CI test pipeline is not configured."),
    ("I4", "DevOps", "Testing and Improvements", "DevOps validation beyond local Compose has not started."),
    ("J1", "Final Testing", "Testing and Improvements", "Full final QA phase has not started."),
]


def document_xml() -> str:
    body: list[str] = []
    body.append(para("WEEKLY STATUS REPORT", style="Title", after=80, keep_next=True))
    body.append(para("Glass RFQ Extraction System - Feature Requirements Status", style="Subtitle", after=220))
    body.append(label_para("Prepared for", "Bilvantis Internship Project"))
    body.append(label_para("Prepared by", "Srikar Devesetti"))
    body.append(label_para("Report date", "July 17, 2026"))
    body.append(label_para("Status basis", "Feature requirements completion after extraction audit, tests, HTML view, docs, and Docker validation"))
    body.append(
        callout(
            "Executive Summary",
            "The extraction core, agent architecture, persistence layer, API, queue framework, Docker Compose setup, audit script, demo guide, and lightweight output view are now in place. Current status is 27 satisfied, 12 partial, and 5 not satisfied requirements out of 44. Remaining work is mainly UI polish, attachment/OCR depth, CI/DevOps automation, final QA, and final documentation polish.",
        )
    )

    body.append(para("Status Snapshot", style="Heading1", keep_next=True))
    body.append(
        table(
            ["Status", "Count", "Current Meaning"],
            [
                ["Satisfied", str(len(DONE)), "Implemented and locally verified or directly covered by tests/audit/demo evidence."],
                ["Partial", str(len(PARTIAL)), "Usable foundation exists, but scope is incomplete or validation is not comprehensive."],
                ["Not Satisfied", str(len(NOT_DONE)), "Feature or phase has not been implemented yet."],
                ["Total", str(len(DONE) + len(PARTIAL) + len(NOT_DONE)), "Total feature requirements tracked."],
            ],
            [1800, 1000, 6560],
        )
    )

    body.append(para("Completed This Session", style="Heading1", keep_next=True))
    body.append(
        table(
            ["Area", "Evidence"],
            [
                ["Extraction run", "Ran all 28 provided fixture emails through claude-opus-4-8 and regenerated JSON/SQLite outputs."],
                ["Audit", "Created audit script; output audit passed with 28 email records, 40 items, and 28 agent runs."],
                ["Accuracy fixes", "Fixed IGU outboard bronze export to TT1 and LIU inboard HS retention for HT3."],
                ["Tests", "Added fixture classification/extraction tests and API view tests. Full suite passes with 31 tests."],
                ["Output view", "Added FastAPI HTML view at /view and per-email detail pages at /view/emails/{email_id}."],
                ["Docs/demo", "Added docs/final_demo.md and updated README, API, and platform docs."],
                ["Docker", "Validated Docker Compose end-to-end with API, Redis, Celery worker, Anthropic call, and PostgreSQL persistence."],
            ],
            [2200, 7160],
        )
    )

    body.append(para("Satisfied Requirements", style="Heading1", keep_next=True))
    body.append(table(["ID", "Section", "Requirement", "Evidence"], [list(item) for item in DONE], [650, 1450, 3000, 4260]))

    body.append(para("Partially Satisfied Requirements", style="Heading1", keep_next=True))
    body.append(table(["ID", "Section", "Requirement", "Remaining Gap"], [list(item) for item in PARTIAL], [650, 1450, 3000, 4260]))

    body.append(para("Not Satisfied Requirements", style="Heading1", keep_next=True))
    body.append(table(["ID", "Section", "Requirement", "Reason"], [list(item) for item in NOT_DONE], [650, 1450, 3000, 4260]))

    body.append(para("Validation Evidence", style="Heading1", keep_next=True))
    body.append(
        table(
            ["Check", "Result"],
            [
                ["Fixture extraction", "28 records processed; 40 glass items extracted; 8 completed and 20 human-review-required."],
                ["JSON/SQLite audit", "Passed. Counts match and output avoids exported field_sources/source and invalid TT values."],
                ["Unit/API tests", "31 tests passed via unittest discovery."],
                ["Compile check", "compileall passed for agent_rfq_extractor, database, scripts, and tests."],
                ["Docker Compose", "Build and startup passed; /health and /view returned 200; queued Celery fixture extraction completed successfully."],
            ],
            [2300, 7060],
        )
    )

    body.append(para("Recommended Next Steps", style="Heading1", keep_next=True))
    body.append(
        table(
            ["Priority", "Action", "Reason"],
            [
                ["1", "Polish UI and attachment display", "The simple output view works, but UI requirements still need stronger user-facing coverage."],
                ["2", "Expand attachment regression coverage", "Text attachment support exists, but real attachment cases and OCR boundary docs need stronger proof."],
                ["3", "Add GitHub Actions CI", "Automated test and Docker build pipelines are the largest remaining DevOps gap."],
                ["4", "Run final QA pass", "Final testing should verify all fixture emails, Gmail path, API path, queue path, and documentation steps."],
                ["5", "Finalize architecture/API/deployment docs", "Existing docs are useful but should be packaged as final submission materials."],
            ],
            [1000, 3000, 5360],
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


def styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/><w:color w:val="000000"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="120" w:line="264" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:sz w:val="48"/><w:color w:val="0B2545"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="220"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="28"/><w:color w:val="555555"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="320" w:after="160"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:sz w:val="32"/><w:color w:val="2E74B5"/></w:rPr></w:style>
</w:styles>"""


def content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
</Types>"""


def rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def document_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>"""


def settings_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/></w:settings>"""


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
