CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS project;

CREATE TABLE IF NOT EXISTS project.agent_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    system_prompt_version VARCHAR(50),
    config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project.artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id UUID REFERENCES project.agent_registry(id),
    artifact_type VARCHAR(50) NOT NULL,
    content JSONB NOT NULL,
    version INTEGER DEFAULT 1,
    phase VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artifacts_agent ON project.artifacts(agent_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_phase ON project.artifacts(phase);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON project.artifacts(artifact_type);

CREATE TABLE IF NOT EXISTS project.mcp_api_keys (
    key_hash    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    preview     TEXT NOT NULL,
    teams       JSONB NOT NULL DEFAULT '["*"]',
    agents      JSONB NOT NULL DEFAULT '["*"]',
    scopes      JSONB NOT NULL DEFAULT '["call_agent"]',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ,
    revoked     BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_api_keys_revoked ON project.mcp_api_keys(revoked);

-- ── HITL (Human-In-The-Loop) requests ────────────
CREATE TABLE IF NOT EXISTS project.hitl_requests (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id     TEXT NOT NULL,
    agent_id      TEXT NOT NULL,
    team_id       TEXT NOT NULL DEFAULT 'default',
    request_type  TEXT NOT NULL CHECK (request_type IN ('approval', 'question')),
    prompt        TEXT NOT NULL,
    context       JSONB DEFAULT '{}',
    channel       TEXT NOT NULL DEFAULT 'discord',
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'answered', 'timeout', 'cancelled')),
    response      TEXT,
    reviewer      TEXT,
    response_channel TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    answered_at   TIMESTAMPTZ,
    expires_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hitl_status ON project.hitl_requests(status);
CREATE INDEX IF NOT EXISTS idx_hitl_team ON project.hitl_requests(team_id);
CREATE INDEX IF NOT EXISTS idx_hitl_created ON project.hitl_requests(created_at DESC);

-- ── HITL Console users ──────────────────────────
CREATE TABLE IF NOT EXISTS project.hitl_users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    is_active     BOOLEAN DEFAULT true,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS project.hitl_team_members (
    id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id  UUID NOT NULL REFERENCES project.hitl_users(id) ON DELETE CASCADE,
    team_id  TEXT NOT NULL,
    role     TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member')),
    UNIQUE(user_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_hitl_tm_user ON project.hitl_team_members(user_id);
CREATE INDEX IF NOT EXISTS idx_hitl_tm_team ON project.hitl_team_members(team_id);

-- Migration: add remind columns if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'project' AND table_name = 'hitl_requests' AND column_name = 'reminded_at'
    ) THEN
        ALTER TABLE project.hitl_requests ADD COLUMN reminded_at TIMESTAMPTZ;
        ALTER TABLE project.hitl_requests ADD COLUMN remind_count INTEGER DEFAULT 0;
    END IF;
END $$;

-- Migration: add scopes column if missing (existing installs)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'project' AND table_name = 'mcp_api_keys' AND column_name = 'scopes'
    ) THEN
        ALTER TABLE project.mcp_api_keys ADD COLUMN scopes JSONB NOT NULL DEFAULT '["call_agent"]';
    END IF;
END $$;
