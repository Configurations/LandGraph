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
