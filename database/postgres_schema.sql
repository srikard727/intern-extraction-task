CREATE TABLE IF NOT EXISTS emails (
    email_id TEXT PRIMARY KEY,
    conv_id TEXT,
    from_email TEXT,
    to_email TEXT,
    subject TEXT,
    body_text TEXT,
    emailbody_variant TEXT,
    received_at TEXT,
    has_attachments BOOLEAN,
    extracted_at TEXT,
    status TEXT,
    review_json JSONB,
    attachments_json JSONB,
    llm_model TEXT,
    raw_json JSONB
);

CREATE TABLE IF NOT EXISTS items (
    id BIGSERIAL PRIMARY KEY,
    email_id TEXT NOT NULL REFERENCES emails(email_id) ON DELETE CASCADE,
    mark TEXT,
    width DOUBLE PRECISION,
    height DOUBLE PRECISION,
    quantity INTEGER,
    shape TEXT,
    TK TEXT,
    HT TEXT,
    TT TEXT,
    color TEXT,
    glass_type TEXT,
    airspace TEXT,
    overall_thickness TEXT,
    gas_fill TEXT,
    coating TEXT,
    edge_work TEXT,
    interlayer TEXT,
    lite_details_json JSONB,
    source TEXT,
    field_sources_json JSONB,
    missing_fields_json JSONB,
    notes TEXT,
    spec_json JSONB,
    raw_json JSONB
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    parent_run_id TEXT,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    email_id TEXT,
    conv_id TEXT,
    error TEXT,
    review_status TEXT,
    item_count INTEGER,
    metadata_json JSONB,
    context_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_items_email_id
    ON items(email_id);
CREATE INDEX IF NOT EXISTS idx_items_glass_type
    ON items(glass_type);
CREATE INDEX IF NOT EXISTS idx_agent_runs_email_id
    ON agent_runs(email_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_name
    ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_runs_started_at
    ON agent_runs(started_at);
