# Platform Setup

The project now supports two database modes:

- SQLite by default for local CLI/API development.
- PostgreSQL when `DATABASE_URL` is set.

## PostgreSQL

Set:

```bash
DATABASE_URL=postgresql://rfq:rfq@localhost:5432/rfq_extractions
```

The PostgreSQL schema is in:

```text
database/postgres_schema.sql
```

It defines:

- `emails`
- `items`
- `agent_runs`

JSON-heavy payloads use `JSONB`; common searchable fields remain first-class
columns.

## Redis And Celery

Redis is used as the Celery broker/result backend.

```bash
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

Start a worker locally:

```bash
.venv/bin/celery -A agent_rfq_extractor.celery_app.celery_app worker --loglevel=INFO
```

Queued API endpoints:

- `POST /tasks/extract/fixture`
- `POST /tasks/extract/gmail`
- `GET /tasks/{task_id}`

Synchronous extraction endpoints remain available:

- `POST /extract/fixture`
- `POST /extract/gmail`

## Docker Compose

Validate the Compose file:

```bash
docker compose config --quiet
```

Start the platform:

```bash
docker compose up --build
```

Services:

- `postgres`: PostgreSQL database
- `redis`: Celery broker/result backend
- `api`: FastAPI app on `http://127.0.0.1:8000`
- `worker`: Celery worker

API docs:

```text
http://127.0.0.1:8000/docs
```

Output view:

```text
http://127.0.0.1:8000/view
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Final QA

Run the local QA suite:

```bash
.venv/bin/python scripts/final_qa.py
```

The script runs:

- unit tests
- Python compile checks
- JSON/SQLite output audit
- `/view` UI validation
- Docker Compose config validation when Docker is available

## GitHub Actions

The CI workflow is defined in:

```text
.github/workflows/ci.yml
```

It runs the Python tests, compile checks, output audit, UI validation, Docker
Compose validation, and Docker image build.
