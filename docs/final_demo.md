# Final Demo Steps

This demo uses the provided `Emails.txt` fixture and writes clean outputs to:

- `outputs/rfq_extractions.db`
- `outputs/rfq_extractions.json`

The latest verified fixture run used `claude-opus-4-8` and produced:

- 28 email records
- 40 extracted glass items
- 10 completed records
- 18 human-review-required records

## 1. Run Extraction

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

Use `--skip-docker` only when Docker is unavailable.

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

Stop services after the demo:

```bash
docker compose down
```
