# Final Demo Steps

This demo uses the provided `Emails.txt` fixture and writes clean outputs to:

- `outputs/rfq_extractions.db`
- `outputs/rfq_extractions.json`

The checked-in acceptance output records `claude-opus-4-8` and contains:

- 28 email records
- 40 extracted glass items
- 8 completed records
- 20 human-review-required records

## 1. Run Extraction

This command sends the synthetic fixture email contents to Anthropic and uses
API credits. Run it only when that external transmission is authorized.

```bash
.venv/bin/python -m agent_rfq_extractor \
  --source fixture \
  --fixture Emails.txt \
  --limit 100 \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --replace-existing
```

## 2. Audit Outputs

```bash
.venv/bin/python scripts/audit_extraction_outputs.py \
  --json outputs/rfq_extractions.json \
  --db outputs/rfq_extractions.db \
  --fixture-expectations
```

Expected result:

```text
JSON records: 28
SQLite rows: emails=28, items=40, agent_runs=28
Audit passed.
```

The audit checks:

- JSON and SQLite row counts match.
- Each extracted unit has a valid shape.
- Exported JSON does not expose `field_sources` or raw `source`.
- TT fields do not contain `body`, attachment labels, or construction labels.
- Fixture-specific cases remain correct, including correction handling, metric conversion, mixed package grouping, outboard bronze on an IGU, and inboard `HS` on an LIU.
- Every supplied fixture email and all 40 expected items match the checked-in acceptance oracle.
- SQLite field provenance is complete and valid, while exported JSON remains clean.

## 3. Review JSON And SQLite

Open the JSON file:

```text
outputs/rfq_extractions.json
```

Useful SQLite checks:

```bash
sqlite3 outputs/rfq_extractions.db 'select status, count(*) from emails group by status;'
sqlite3 outputs/rfq_extractions.db 'select glass_type, count(*) from items group by glass_type order by glass_type;'
sqlite3 outputs/rfq_extractions.db 'select count(*) from agent_runs;'
```

## 4. Start API And Output View

```bash
.venv/bin/uvicorn agent_rfq_extractor.api:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/view
```

Useful demo records:

- `fixture-018`: four glass-type groups from one package.
- `fixture-019`: monolithic, laminated, insulated, and laminated-insulated units in one email.
- `fixture-022`: latest correction changes thickness from `1/4"` to `3/8"`.
- `fixture-023`: reorder-only request correctly produces no invented item and requires human review.
- `fixture-024`: metric dimensions normalize from `600mm x 1500mm` to decimal inches.

For an attachment-origin demonstration, use `fixtures/attachment_demo.txt`.
The corresponding text schedule lives under `fixtures/attachments/`; after
extraction, open `/emails/fixture-001/sources` or the UI detail page to show
`attachment:glass_schedule.txt` provenance.

Use separate outputs so the attachment demo does not replace the 28-email
acceptance artifacts:

```bash
.venv/bin/python -m agent_rfq_extractor \
  --source fixture \
  --fixture fixtures/attachment_demo.txt \
  --db /tmp/rfq_attachment_demo.db \
  --json /tmp/rfq_attachment_demo.json \
  --replace-existing
```

For the image-only attachment demonstration, use the three generated RFQ PDFs:

```bash
.venv/bin/python scripts/generate_image_pdf_fixtures.py
.venv/bin/python -m agent_rfq_extractor \
  --source fixture \
  --fixture fixtures/image_pdf_rfq_emails.txt \
  --db /tmp/rfq_image_pdf_demo.db \
  --json /tmp/rfq_image_pdf_demo.json \
  --replace-existing
```

The first PDF contains two monolithic marks, the second contains one insulated
unit, and the third intentionally leaves the second laminated lite's heat
treatment pending. In the UI, verify `Extraction = ocr`, confidence at or above
90% for the clean fixture pages, `attachment:<filename>` provenance, and human
review for the pending laminated field.

## 5. Validate UI Routes

```bash
.venv/bin/python scripts/validate_ui.py \
  --db outputs/rfq_extractions.db \
  --json outputs/rfq_extractions.json \
  --fixture-expectations
```

Expected result:

```text
UI validation passed.
```

## 6. Run Final QA

```bash
.venv/bin/python scripts/final_qa.py
```

When Docker Desktop is running, use:

```bash
.venv/bin/python scripts/final_qa.py --docker-build
```

Use `--skip-docker` only when Docker is unavailable.

Expected local result before Docker:

```text
Final QA passed.
```

The local QA suite includes unit tests, attachment tests, Celery task tests,
compile checks, JSON/SQLite audit, and UI validation.

## 7. Docker Compose Validation

After local extraction, validate the platform:

```bash
docker compose up --build
```

Then check:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/view
```

Load the accepted 28-email dataset into the running PostgreSQL platform without
another model call:

```bash
.venv/bin/python scripts/import_sqlite_results.py \
  --source-db outputs/rfq_extractions.db \
  --database-url postgresql://rfq:rfq@127.0.0.1:5432/rfq_extractions \
  --json /tmp/rfq_postgres_export.json \
  --replace
docker compose cp \
  /tmp/rfq_postgres_export.json \
  api:/app/outputs/rfq_extractions.json
```

Refresh `/view`; it should show 28 emails, 40 items, 8 completed records, and
20 human-review-required records.

Stop services after the demo:

```bash
docker compose down
```

Latest infrastructure revalidation completed on August 19, 2026:

- Compose rebuilt and started PostgreSQL, Redis, API, and worker.
- API health and `/view` returned successfully with the Opus model configured.
- Redis and the Celery worker responded; worker concurrency was capped at 2.
- Tesseract 5.5 was present in both application containers, and the three
  raster-only RFQ PDFs completed OCR inside the API container at 93-94%
  measured confidence.
- API and worker ran as non-root and shared a writable output volume.
- PostgreSQL and the shared JSON volume contained the accepted 28 emails,
  40 items, and 28 agent runs after deterministic import.
- Synchronous and queued extraction paths were previously verified with a
  one-email smoke fixture.
