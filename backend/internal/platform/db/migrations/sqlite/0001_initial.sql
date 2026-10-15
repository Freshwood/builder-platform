-- Users (guests for now), projects as JSON documents, the append-only command log and the
-- stored agent runs (ADR-0002, ADR-0005).
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    display_name TEXT,
    is_guest INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX ix_projects_owner_id ON projects (owner_id);

CREATE TABLE project_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    command TEXT NOT NULL,
    actor TEXT NOT NULL,
    llm_trace_id TEXT,
    engine_version TEXT NOT NULL,
    design_version TEXT NOT NULL,
    diff TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (project_id, seq)
);
CREATE INDEX ix_project_commands_project_id ON project_commands (project_id);

CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY,
    trace_id TEXT NOT NULL UNIQUE,
    owner_id TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    chat_id TEXT,
    project_id TEXT REFERENCES projects (id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_fingerprint TEXT,
    safety_rules_version TEXT,
    model_role TEXT,
    routing_reason TEXT,
    duration_ms INTEGER,
    ui_messages TEXT NOT NULL,
    model_messages TEXT,
    design_attempts TEXT NOT NULL,
    usage TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX ix_agent_runs_owner_id ON agent_runs (owner_id);
CREATE INDEX ix_agent_runs_chat_id ON agent_runs (chat_id);
CREATE INDEX ix_agent_runs_project_id ON agent_runs (project_id);
