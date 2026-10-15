-- Users (guests for now), projects as JSONB documents, the append-only command log and the
-- stored agent runs (ADR-0002, ADR-0005).
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(320) UNIQUE,
    display_name VARCHAR(120),
    is_guest BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE projects (
    id UUID PRIMARY KEY,
    owner_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    schema_version INTEGER NOT NULL,
    model JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_projects_owner_id ON projects (owner_id);

CREATE TABLE project_commands (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    command JSONB NOT NULL,
    actor VARCHAR(16) NOT NULL,
    llm_trace_id VARCHAR(64),
    engine_version VARCHAR(32) NOT NULL,
    design_version VARCHAR(32) NOT NULL,
    diff JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (project_id, seq)
);
CREATE INDEX ix_project_commands_project_id ON project_commands (project_id);

CREATE TABLE agent_runs (
    id UUID PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL UNIQUE,
    owner_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    chat_id VARCHAR(128),
    project_id UUID REFERENCES projects (id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL,
    model VARCHAR(128) NOT NULL,
    prompt_version VARCHAR(32) NOT NULL,
    prompt_fingerprint VARCHAR(32),
    safety_rules_version VARCHAR(16),
    model_role VARCHAR(16),
    routing_reason VARCHAR(32),
    duration_ms INTEGER,
    ui_messages JSONB NOT NULL,
    model_messages JSONB,
    design_attempts JSONB NOT NULL,
    usage JSONB,
    error VARCHAR(2000),
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_agent_runs_owner_id ON agent_runs (owner_id);
CREATE INDEX ix_agent_runs_chat_id ON agent_runs (chat_id);
CREATE INDEX ix_agent_runs_project_id ON agent_runs (project_id);
