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
    password_hash TEXT,
    display_name  TEXT NOT NULL DEFAULT '',
    role          TEXT NOT NULL DEFAULT 'undefined' CHECK (role IN ('admin', 'member', 'undefined')),
    auth_type     TEXT NOT NULL DEFAULT 'local' CHECK (auth_type IN ('local', 'google')),
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

-- ── Outline document tracking ─────────────────────
CREATE TABLE IF NOT EXISTS project.outline_documents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id     TEXT NOT NULL,
    team_id       TEXT NOT NULL DEFAULT 'default',
    agent_id      TEXT NOT NULL,
    phase         TEXT NOT NULL,
    deliverable_key TEXT NOT NULL,
    outline_document_id TEXT,
    outline_url   TEXT,
    version       INTEGER DEFAULT 1,
    content_hash  TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(thread_id, team_id, phase, deliverable_key)
);

CREATE INDEX IF NOT EXISTS idx_outline_docs_thread ON project.outline_documents(thread_id);
CREATE INDEX IF NOT EXISTS idx_outline_docs_team ON project.outline_documents(team_id);

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

-- ── Production Manager tables ────────────────────
CREATE TABLE IF NOT EXISTS project.pm_issue_counters (
    team_id TEXT PRIMARY KEY,
    next_seq INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS project.pm_projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    lead TEXT NOT NULL,
    team_id TEXT NOT NULL,
    color TEXT DEFAULT '#6366f1',
    status TEXT DEFAULT 'on-track' CHECK (status IN ('on-track', 'at-risk', 'off-track')),
    start_date DATE,
    target_date DATE,
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project.pm_project_members (
    project_id INTEGER REFERENCES project.pm_projects(id) ON DELETE CASCADE,
    user_name TEXT NOT NULL,
    role TEXT DEFAULT 'member' CHECK (role IN ('lead', 'member')),
    PRIMARY KEY(project_id, user_name)
);

CREATE TABLE IF NOT EXISTS project.pm_issues (
    id TEXT PRIMARY KEY,
    project_id INTEGER REFERENCES project.pm_projects(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'backlog' CHECK (status IN ('backlog', 'todo', 'in-progress', 'in-review', 'done')),
    priority INTEGER DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
    assignee TEXT,
    team_id TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pm_issues_project ON project.pm_issues(project_id);
CREATE INDEX IF NOT EXISTS idx_pm_issues_status ON project.pm_issues(status);
CREATE INDEX IF NOT EXISTS idx_pm_issues_team ON project.pm_issues(team_id);
CREATE INDEX IF NOT EXISTS idx_pm_issues_assignee ON project.pm_issues(assignee);

CREATE TABLE IF NOT EXISTS project.pm_issue_relations (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('blocks', 'relates-to', 'parent', 'duplicates')),
    source_issue_id TEXT NOT NULL REFERENCES project.pm_issues(id) ON DELETE CASCADE,
    target_issue_id TEXT NOT NULL REFERENCES project.pm_issues(id) ON DELETE CASCADE,
    reason TEXT DEFAULT '',
    created_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(type, source_issue_id, target_issue_id)
);
CREATE INDEX IF NOT EXISTS idx_pm_relations_source ON project.pm_issue_relations(source_issue_id);
CREATE INDEX IF NOT EXISTS idx_pm_relations_target ON project.pm_issue_relations(target_issue_id);

CREATE TABLE IF NOT EXISTS project.pm_pull_requests (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    issue_id TEXT REFERENCES project.pm_issues(id) ON DELETE SET NULL,
    status TEXT DEFAULT 'draft' CHECK (status IN ('pending', 'approved', 'changes_requested', 'draft')),
    additions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    files INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project.pm_inbox (
    id SERIAL PRIMARY KEY,
    user_email TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('mention', 'assign', 'comment', 'status', 'review', 'blocked', 'unblocked', 'dependency_added')),
    text TEXT NOT NULL,
    issue_id TEXT,
    related_issue_id TEXT,
    relation_type TEXT,
    avatar TEXT,
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pm_inbox_user ON project.pm_inbox(user_email, read, created_at DESC);

CREATE TABLE IF NOT EXISTS project.pm_activity (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES project.pm_projects(id) ON DELETE CASCADE,
    user_name TEXT NOT NULL,
    action TEXT NOT NULL,
    issue_id TEXT,
    detail TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pm_activity_project ON project.pm_activity(project_id, created_at DESC);

-- Migration: add auth_type column + allow nullable password_hash + undefined role
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'project' AND table_name = 'hitl_users' AND column_name = 'auth_type'
    ) THEN
        ALTER TABLE project.hitl_users ADD COLUMN auth_type TEXT NOT NULL DEFAULT 'local';
        ALTER TABLE project.hitl_users ALTER COLUMN password_hash DROP NOT NULL;
        -- Update role constraint to include 'undefined'
        ALTER TABLE project.hitl_users DROP CONSTRAINT IF EXISTS hitl_users_role_check;
        ALTER TABLE project.hitl_users ADD CONSTRAINT hitl_users_role_check CHECK (role IN ('admin', 'member', 'undefined'));
        -- Add auth_type constraint
        ALTER TABLE project.hitl_users ADD CONSTRAINT hitl_users_auth_type_check CHECK (auth_type IN ('local', 'google'));
    END IF;
END $$;

-- Migration: add phase column to pm_issues
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'project' AND table_name = 'pm_issues' AND column_name = 'phase'
    ) THEN
        ALTER TABLE project.pm_issues ADD COLUMN phase TEXT;
        CREATE INDEX idx_pm_issues_phase ON project.pm_issues(phase);
    END IF;
END $$;
