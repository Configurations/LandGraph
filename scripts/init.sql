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
