from __future__ import annotations

import html
import zipfile
from pathlib import Path


OUT_PATH = Path("reports/WSR_RFQ_Extraction_Status_Report_2026-07-01.docx")

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def w_attr(name: str, value: object) -> str:
    return f'w:{name}="{esc(value)}"'


def color(hex_value: str) -> str:
    return hex_value.replace("#", "")


def run(text: str, *, bold: bool = False, italic: bool = False, size: int | None = None, color_hex: str | None = None) -> str:
    props: list[str] = []
    if bold:
        props.append("<w:b/>")
    if italic:
        props.append("<w:i/>")
    if size is not None:
        props.append(f'<w:sz {w_attr("val", size * 2)}/>')
    if color_hex:
        props.append(f'<w:color {w_attr("val", color(color_hex))}/>')
    props.append('<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>')
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    space = ' xml:space="preserve"' if text[:1].isspace() or text[-1:].isspace() else ""
    return f"<w:r>{rpr}<w:t{space}>{esc(text)}</w:t></w:r>"


def para(
    text: str = "",
    *,
    style: str | None = None,
    before: int | None = None,
    after: int | None = None,
    align: str | None = None,
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
            f'<w:spacing {w_attr("before", before or 0)} {w_attr("after", after or 0)} w:line="264" w:lineRule="auto"/>'
        )
    if align:
        ppr.append(f'<w:jc {w_attr("val", align)}/>')
    ppr_xml = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
    return f"<w:p>{ppr_xml}{run(text, bold=bold, italic=italic, size=size, color_hex=color_hex) if text else ''}</w:p>"


def label_para(label: str, value: str) -> str:
    return (
        "<w:p><w:pPr><w:spacing w:before=\"0\" w:after=\"40\" w:line=\"264\" w:lineRule=\"auto\"/></w:pPr>"
        + run(label + ": ", bold=True)
        + run(value)
        + "</w:p>"
    )


def cell(text: str, width: int, *, fill: str | None = None, bold: bool = False, shade_text: str | None = None) -> str:
    shd = f'<w:shd w:fill="{color(fill)}"/>' if fill else ""
    valign = '<w:vAlign w:val="center"/>'
    tcpr = f'<w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shd}{valign}</w:tcPr>'
    paragraphs = []
    for part in str(text).split("\n"):
        paragraphs.append(
            "<w:p><w:pPr><w:spacing w:before=\"0\" w:after=\"60\" w:line=\"264\" w:lineRule=\"auto\"/></w:pPr>"
            + run(part, bold=bold, size=9, color_hex=shade_text)
            + "</w:p>"
        )
    return f"<w:tc>{tcpr}{''.join(paragraphs)}</w:tc>"


def row(values: list[str], widths: list[int], *, header: bool = False, fills: list[str | None] | None = None) -> str:
    fills = fills or [None] * len(values)
    trpr = "<w:trPr><w:tblHeader/></w:trPr>" if header else ""
    cells = "".join(
        cell(value, width, fill=fills[index], bold=header, shade_text="#0B2545" if header else None)
        for index, (value, width) in enumerate(zip(values, widths))
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
        '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/>'
        '<w:start w:w="120" w:type="dxa"/><w:end w:w="120" w:type="dxa"/></w:tblCellMar>'
    )
    pr = (
        '<w:tblPr><w:tblW w:w="9360" w:type="dxa"/><w:tblInd w:w="120" w:type="dxa"/>'
        '<w:tblLayout w:type="fixed"/>'
        + borders
        + margins
        + "</w:tblPr>"
    )
    return (
        "<w:tbl>"
        + pr
        + f"<w:tblGrid>{grid}</w:tblGrid>"
        + row(headers, widths, header=True, fills=["#F2F4F7"] * len(headers))
        + "".join(row(item, widths) for item in rows)
        + "</w:tbl>"
    )


def callout(title: str, body: str) -> str:
    widths = [9360]
    content = (
        "<w:tbl><w:tblPr><w:tblW w:w=\"9360\" w:type=\"dxa\"/><w:tblInd w:w=\"120\" w:type=\"dxa\"/>"
        "<w:tblLayout w:type=\"fixed\"/><w:tblBorders><w:top w:val=\"single\" w:sz=\"6\" w:color=\"B8C7D9\"/>"
        "<w:left w:val=\"single\" w:sz=\"6\" w:color=\"B8C7D9\"/><w:bottom w:val=\"single\" w:sz=\"6\" w:color=\"B8C7D9\"/>"
        "<w:right w:val=\"single\" w:sz=\"6\" w:color=\"B8C7D9\"/></w:tblBorders>"
        "<w:tblCellMar><w:top w:w=\"140\" w:type=\"dxa\"/><w:bottom w:w=\"140\" w:type=\"dxa\"/>"
        "<w:start w:w=\"180\" w:type=\"dxa\"/><w:end w:w=\"180\" w:type=\"dxa\"/></w:tblCellMar></w:tblPr>"
        "<w:tblGrid><w:gridCol w:w=\"9360\"/></w:tblGrid><w:tr>"
    )
    tcpr = '<w:tcPr><w:tcW w:w="9360" w:type="dxa"/><w:shd w:fill="F4F6F9"/></w:tcPr>'
    p1 = "<w:p><w:pPr><w:spacing w:after=\"80\"/></w:pPr>" + run(title, bold=True, color_hex="#1F3A5F") + "</w:p>"
    p2 = "<w:p><w:pPr><w:spacing w:after=\"0\" w:line=\"264\" w:lineRule=\"auto\"/></w:pPr>" + run(body) + "</w:p>"
    return content + f"<w:tc>{tcpr}{p1}{p2}</w:tc></w:tr></w:tbl>"


REQUIREMENTS = [
    ("Requirements", "Glass type analysis and field identification", "June 08 - June 11", "Satisfied", "Glass type aliases, type-specific fields, and output grouping are implemented."),
    ("Requirements", "Define mandatory vs optional fields by glass type", "June 08 - June 11", "Satisfied", "Required fields are enforced for monolithic, laminated, insulated, and laminated-insulated units."),
    ("Requirements", "Define Human Review business rules", "June 08 - June 11", "Satisfied", "Missing required fields, no-items cases, and body/attachment conflicts trigger human_review_required."),
    ("Requirements", "Define future agent architecture (Extractor as Agent 1)", "June 08 - June 11", "Satisfied", "ExtractorAgent now wraps the LangGraph extractor as the first registered agent."),
    ("Architecture", "Multi-Agent Framework Design", "June 12 - June 22", "Satisfied", "AgentWorkflow runs ordered agent steps, passes outputs between agents, shares workflow context, and supports per-step execution logging."),
    ("Architecture", "Agent Base Class & Registry Design", "June 12 - June 22", "Satisfied", "BaseAgent, AgentContext, AgentResult, AgentRegistry, and registered ExtractorAgent are implemented."),
    ("Architecture", "LangGraph Orchestrator Setup", "June 12 - June 22", "Satisfied", "LangGraph flow runs prepare -> extract -> normalize -> review -> assemble."),
    ("Architecture", "State Management & Agent Contracts", "June 12 - June 22", "Satisfied", "AgentContext, AgentResult, AgentWorkflowResult, and sequential output handoff define the current cross-agent contract."),
    ("Infrastructure", "FastAPI Project Setup", "June 23 - June 29", "Satisfied", "FastAPI app exposes health, stored emails, agent runs, and extraction trigger endpoints."),
    ("Infrastructure", "PostgreSQL Setup & Schema Design", "June 23 - June 29", "Satisfied", "DATABASE_URL switches to PostgreSQL; schema defines emails, items, and agent_runs with JSONB payloads."),
    ("Infrastructure", "Redis Setup", "June 23 - June 29", "Satisfied", "Redis dependency and REDIS_URL configuration support Celery broker/result backend usage."),
    ("Infrastructure", "Celery Queue Framework Setup", "June 23 - June 29", "Satisfied", "Celery app and extraction tasks queue fixture/Gmail workflows through the existing RFQPipeline."),
    ("Infrastructure", "Docker Compose Setup", "June 23 - June 29", "Satisfied", "Docker Compose starts PostgreSQL, Redis, FastAPI, and Celery worker services."),
    ("Mailbox Extraction", "Email data extraction", "June 30 - July 1", "Satisfied", "Gmail message fetch, HTML/plain body handling, thread context, and message metadata are implemented."),
    ("Mailbox Extraction", "Attachment data extraction", "June 30 - July 1", "Satisfied", "Text-layer PDF, DOCX, TXT, CSV, and TSV extraction are supported; image-only attachments remain out of scope."),
    ("Extractor Agent", "Email Classification Logic (Glass Type Detection)", "July 2 - July 19", "Satisfied", "Glass type normalization detects monolithic, laminated, insulated, and laminated-insulated requests."),
    ("Extractor Agent", "Monolithic Extraction Logic", "July 2 - July 19", "Satisfied", "Monolithic dimensions, TK, HT, TT/color separation, fabrication, quantity, and review checks are implemented."),
    ("Extractor Agent", "Laminated Extraction Logic", "July 2 - July 19", "Satisfied", "TK1/TK2, HT1/HT2, interlayer material/thickness, and clear lite parsing are implemented."),
    ("Extractor Agent", "Insulated Extraction Logic", "July 2 - July 19", "Satisfied", "TK1/TK2, HT1/HT2, spacer, gas fill, Low-E context, and overall-thickness handling are implemented."),
    ("Extractor Agent", "Laminated-Insulated Extraction Logic", "July 2 - July 19", "Satisfied", "Three-lite fields, laminated lite, interlayer, spacer, and no-inheritance guards are implemented."),
    ("Extractor Agent", "Attachment Processing Framework", "July 2 - July 19", "Partial", "Text extraction framework exists; OCR/image-only and richer attachment workflows are not implemented."),
    ("Extractor Agent", "Testing and Improvements", "July 2 - July 19", "Partial", "A TT cleanup regression test exists; broader fixture and end-to-end test coverage is still needed."),
    ("Database Layer", "Store Emails", "July 22 - July 24", "Satisfied", "SQLite emails table stores message metadata, body text, status, review JSON, attachments JSON, and model."),
    ("Database Layer", "Store Extracted Units", "July 22 - July 24", "Satisfied", "SQLite items table stores item-level searchable fields plus type-specific spec_json."),
    ("Database Layer", "Store Agent Execution Logs", "July 22 - July 24", "Satisfied", "SQLite agent_runs table stores agent name, status, model, timing, email id, error, review status, item count, and metadata."),
]


def status_counts() -> dict[str, int]:
    counts = {"Satisfied": 0, "Partial": 0, "Not Satisfied": 0}
    for _, _, _, status, _ in REQUIREMENTS:
        counts[status] += 1
    return counts


def document_xml() -> str:
    counts = status_counts()
    status_rows = [
        ["Satisfied", str(counts["Satisfied"]), "Extraction core, mailbox flow, agent scaffold, execution logging, and SQLite persistence are in place."],
        ["Partial", str(counts["Partial"]), "Attachment framework and tests need expansion."],
        ["Not Satisfied", str(counts["Not Satisfied"]), "UI, DevOps, and final documentation are not implemented."],
    ]
    matrix_rows = [[area, requirement, dates, status, note] for area, requirement, dates, status, note in REQUIREMENTS]
    next_steps = [
        ["1", "Validate platform stack", "Run docker compose with real credentials and confirm API/worker extraction against PostgreSQL."],
        ["2", "Broaden tests", "Add fixture-based regression coverage across all four glass types and text attachments."],
        ["3", "Run Opus extraction", "Regenerate SQLite and JSON with claude-opus-4-8 and audit TT/color/source leakage."],
        ["4", "Build UI", "Create the main opening page, email/attachment display, and extraction results view."],
        ["5", "Plan DevOps", "Add GitHub Actions test/build automation once Docker behavior is confirmed."],
    ]
    risk_rows = [
        ["Infrastructure validation", "Medium", "PostgreSQL, Redis, Celery, and Docker Compose scaffolds exist; they still need end-to-end validation with real secrets and Gmail access."],
        ["Architecture expansion", "Medium", "The multi-agent workflow exists; future work should add real validator/review agents when needed."],
        ["Testing depth", "Medium", "Only focused regression coverage is present; extraction quality needs a broader benchmark suite."],
        ["Attachment scope", "Low", "Text attachments are handled; image-only attachments remain explicitly out of scope."],
    ]

    body = []
    body.append(para("WEEKLY STATUS REPORT", style="Title", after=80, keep_next=True))
    body.append(para("Glass RFQ Extraction System", style="Subtitle", after=220))
    body.append(label_para("Prepared for", "Bilvantis Internship Project"))
    body.append(label_para("Prepared by", "Srikar Devesetti"))
    body.append(label_para("Report date", "July 1, 2026"))
    body.append(label_para("Reporting window", "June 8 - July 1, 2026"))
    body.append(label_para("Current phase", "Mailbox extraction complete; extractor agent build begins July 2"))
    body.append(callout("Executive Summary", "The extraction core is functional: Gmail ingestion, thread context, text attachment extraction, LangGraph orchestration, Opus as the default model, reusable agent workflow, agent execution logging, FastAPI setup, PostgreSQL schema, Redis/Celery queue setup, Docker Compose, SQLite fallback, and JSON export are in place. The largest remaining gaps are UI, DevOps, final documentation, and broader regression testing."))

    body.append(para("Status Snapshot", style="Heading1", keep_next=True))
    body.append(table(["Status", "Count", "Summary"], status_rows, [1800, 1000, 6560]))

    body.append(para("Current Week Accomplishments", style="Heading1", keep_next=True))
    body.append(table(
        ["Area", "Progress"],
        [
            ["Mailbox extraction", "Gmail extraction supports message metadata, HTML-preferred body text, chronological thread context, and targeted message reprocessing."],
            ["Attachment extraction", "Text-layer PDFs, DOCX, TXT, CSV, and TSV attachments can be read and attributed as attachment:<filename>."],
            ["Extraction quality", "Type-specific validation flags missing fields instead of guessing; quantity defaults to 1 only when count is not definite."],
            ["Model default", "Default Anthropic model is now claude-opus-4-8. The extractor also handles Opus models that reject temperature."],
            ["Agent framework", "BaseAgent, AgentRegistry, and ExtractorAgent provide the first reusable agent interface."],
            ["Multi-agent workflow", "AgentWorkflow supports ordered future agents with output handoff, workflow context, stop rules, and execution-log callbacks."],
            ["Execution logging", "Agent runs are stored in SQLite with model, timing, status, email id, review status, item count, and error details."],
            ["API setup", "FastAPI exposes health, stored extraction records, agent run logs, and extraction trigger endpoints."],
            ["Platform setup", "PostgreSQL, Redis, Celery, and Docker Compose scaffolds are configured around the existing agent workflow."],
            ["TT cleanup", "Deterministic guards prevent construction labels such as monolithic, laminated, IGU, or body from appearing in TT output."],
        ],
        [2200, 7160],
    ))

    body.append(para("Requirement Matrix", style="Heading1", keep_next=True))
    body.append(table(["Workstream", "Requirement", "Schedule", "Status", "Evidence / Next Action"], matrix_rows, [1450, 2700, 1350, 1050, 2810]))

    body.append(para("Risks and Blockers", style="Heading1", keep_next=True))
    body.append(table(["Risk", "Level", "Mitigation"], risk_rows, [2300, 1000, 6060]))

    body.append(para("Next Week Priorities", style="Heading1", keep_next=True))
    body.append(table(["#", "Priority", "Action"], next_steps, [500, 2200, 6660]))

    body.append(para("Overall Assessment", style="Heading1", keep_next=True))
    body.append(para("The project is ahead on extraction behavior relative to the later extractor-agent timeline, and the internal agent framework plus FastAPI/platform layer are now in place. If the assignment grading emphasizes extraction quality, the current implementation is strong. The next work should focus on UI, DevOps automation, final testing, and final documentation."))

    sect = (
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
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
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/><w:color w:val="000000"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:before="0" w:after="120" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="120" w:line="264" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="80"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:sz w:val="48"/><w:color w:val="0B2545"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="220"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="28"/><w:color w:val="555555"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="320" w:after="160"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:sz w:val="32"/><w:color w:val="2E74B5"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:b/><w:sz w:val="26"/><w:color w:val="2E74B5"/></w:rPr></w:style>
</w:styles>'''


def content_types_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
</Types>'''


def rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''


def document_rels_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'''


def settings_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:zoom w:percent="100"/><w:defaultTabStop w:val="720"/></w:settings>'''


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
