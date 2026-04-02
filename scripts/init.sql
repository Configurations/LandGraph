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
    status TEXT DEFAULT 'on-track' CHECK (status IN ('on-track', 'at-risk', 'off-track', 'paused', 'completed')),
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

-- ── Dispatcher tables ─────────────────────────────

CREATE TABLE IF NOT EXISTS project.dispatcher_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    team_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    project_slug TEXT,
    phase TEXT,
    iteration INTEGER DEFAULT 1,
    instruction TEXT NOT NULL,
    context JSONB DEFAULT '{}',
    previous_answers JSONB DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'waiting_hitl', 'success', 'failure', 'timeout', 'cancelled')),
    container_id TEXT,
    docker_image TEXT NOT NULL,
    cost_usd NUMERIC(10, 4) DEFAULT 0,
    timeout_seconds INTEGER DEFAULT 300,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_disp_tasks_status ON project.dispatcher_tasks(status);
CREATE INDEX IF NOT EXISTS idx_disp_tasks_project ON project.dispatcher_tasks(project_slug, phase);
CREATE INDEX IF NOT EXISTS idx_disp_tasks_agent ON project.dispatcher_tasks(agent_id, team_id);

CREATE TABLE IF NOT EXISTS project.dispatcher_task_events (
    id SERIAL PRIMARY KEY,
    task_id UUID REFERENCES project.dispatcher_tasks(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('progress', 'artifact', 'question', 'result')),
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_disp_events_task ON project.dispatcher_task_events(task_id, created_at);

CREATE TABLE IF NOT EXISTS project.dispatcher_task_artifacts (
    id SERIAL PRIMARY KEY,
    task_id UUID REFERENCES project.dispatcher_tasks(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    deliverable_type TEXT NOT NULL,
    file_path TEXT,
    git_branch TEXT,
    category TEXT,
    status TEXT DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    review_comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_disp_artifacts_task ON project.dispatcher_task_artifacts(task_id);
CREATE INDEX IF NOT EXISTS idx_disp_artifacts_status ON project.dispatcher_task_artifacts(status);

CREATE TABLE IF NOT EXISTS project.dispatcher_cost_summary (
    id SERIAL PRIMARY KEY,
    project_slug TEXT NOT NULL,
    team_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    total_cost_usd NUMERIC(10, 4) DEFAULT 0,
    task_count INTEGER DEFAULT 0,
    avg_cost_per_task NUMERIC(10, 4) DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (project_slug, team_id, phase, agent_id)
);

-- Trigger: notify when HITL request is answered (for dispatcher listener)
CREATE OR REPLACE FUNCTION notify_hitl_response()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status = 'pending' AND NEW.status = 'answered' THEN
        PERFORM pg_notify('hitl_response', json_build_object(
            'request_id', NEW.id,
            'team_id', NEW.team_id,
            'response', LEFT(NEW.response, 4000),
            'reviewer', NEW.reviewer
        )::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_hitl_response ON project.hitl_requests;
CREATE TRIGGER trigger_hitl_response
    AFTER UPDATE ON project.hitl_requests
    FOR EACH ROW
    EXECUTE FUNCTION notify_hitl_response();

-- ── Phase 2a: Project + RAG tables ────────────────

-- Extend pm_projects with new columns
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='pm_projects' AND column_name='slug') THEN
        ALTER TABLE project.pm_projects ADD COLUMN slug TEXT DEFAULT '';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='pm_projects' AND column_name='git_service') THEN
        ALTER TABLE project.pm_projects ADD COLUMN git_service TEXT DEFAULT 'other';
        ALTER TABLE project.pm_projects ADD COLUMN git_url TEXT DEFAULT '';
        ALTER TABLE project.pm_projects ADD COLUMN git_login TEXT DEFAULT '';
        ALTER TABLE project.pm_projects ADD COLUMN git_token_env TEXT DEFAULT '';
        ALTER TABLE project.pm_projects ADD COLUMN git_repo_name TEXT DEFAULT '';
        ALTER TABLE project.pm_projects ADD COLUMN language TEXT DEFAULT 'fr';
        ALTER TABLE project.pm_projects ADD COLUMN rag_collection TEXT DEFAULT '';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS project.rag_documents (
    id SERIAL PRIMARY KEY,
    project_slug TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rag_docs_project ON project.rag_documents(project_slug);

-- IVFFlat index for cosine similarity (needs rows first, created conditionally)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_rag_docs_embedding') THEN
        BEGIN
            CREATE INDEX idx_rag_docs_embedding ON project.rag_documents
                USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
        EXCEPTION WHEN others THEN
            RAISE NOTICE 'IVFFlat index skipped (needs data first): %', SQLERRM;
        END;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS project.rag_conversations (
    id SERIAL PRIMARY KEY,
    project_slug TEXT NOT NULL,
    task_id UUID,
    sender TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rag_conv_project ON project.rag_conversations(project_slug, created_at);

-- ── Phase 2b: Deliverable remarks + budget ────────
CREATE TABLE IF NOT EXISTS project.deliverable_remarks (
    id SERIAL PRIMARY KEY,
    artifact_id INTEGER REFERENCES project.dispatcher_task_artifacts(id) ON DELETE CASCADE,
    reviewer TEXT NOT NULL,
    comment TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_remarks_artifact ON project.deliverable_remarks(artifact_id, created_at);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='pm_projects' AND column_name='budget') THEN
        ALTER TABLE project.pm_projects ADD COLUMN budget NUMERIC(10,2) DEFAULT 0;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='pm_projects' AND column_name='analysis_task_id') THEN
        ALTER TABLE project.pm_projects ADD COLUMN analysis_task_id TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='pm_projects' AND column_name='analysis_status') THEN
        ALTER TABLE project.pm_projects ADD COLUMN analysis_status TEXT DEFAULT 'not_started';
    END IF;
END $$;

-- ── Phase 3a: PM inbox notification trigger ───────
CREATE OR REPLACE FUNCTION notify_pm_inbox() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('pm_inbox', json_build_object(
        'user_email', NEW.user_email,
        'type', NEW.type,
        'issue_id', COALESCE(NEW.issue_id, '')
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_pm_inbox ON project.pm_inbox;
CREATE TRIGGER trigger_pm_inbox
    AFTER INSERT ON project.pm_inbox
    FOR EACH ROW EXECUTE FUNCTION notify_pm_inbox();

-- ── Phase 3b: PR enhancements ─────────────────────
DO $$
BEGIN
    ALTER TABLE project.pm_pull_requests DROP CONSTRAINT IF EXISTS pm_pull_requests_status_check;
    ALTER TABLE project.pm_pull_requests ADD CONSTRAINT pm_pull_requests_status_check
        CHECK (status IN ('pending', 'approved', 'changes_requested', 'draft', 'merged'));
EXCEPTION WHEN others THEN NULL;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='pm_pull_requests' AND column_name='branch') THEN
        ALTER TABLE project.pm_pull_requests ADD COLUMN branch TEXT DEFAULT '';
        ALTER TABLE project.pm_pull_requests ADD COLUMN remote_url TEXT DEFAULT '';
        ALTER TABLE project.pm_pull_requests ADD COLUMN project_slug TEXT DEFAULT '';
        ALTER TABLE project.pm_pull_requests ADD COLUMN merged_by TEXT;
        ALTER TABLE project.pm_pull_requests ADD COLUMN merged_at TIMESTAMPTZ;
    END IF;
END $$;

-- ── Phase 4: Multi-workflow + Automation ───────────

CREATE TABLE IF NOT EXISTS project.project_workflows (
    id SERIAL PRIMARY KEY,
    project_slug TEXT NOT NULL,
    workflow_name TEXT NOT NULL,
    workflow_type TEXT NOT NULL DEFAULT 'custom'
        CHECK (workflow_type IN ('onboarding', 'development', 'audit', 'evolution', 'custom')),
    workflow_json_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'paused', 'completed', 'cancelled')),
    mode TEXT NOT NULL DEFAULT 'sequential'
        CHECK (mode IN ('sequential', 'parallel', 'recurring')),
    priority INTEGER NOT NULL DEFAULT 50,
    iteration INTEGER NOT NULL DEFAULT 1,
    depends_on_workflow_id INTEGER REFERENCES project.project_workflows(id),
    config JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (project_slug, workflow_name, iteration)
);
CREATE INDEX IF NOT EXISTS idx_proj_wf_slug ON project.project_workflows(project_slug, status);
CREATE INDEX IF NOT EXISTS idx_proj_wf_type ON project.project_workflows(workflow_type);

CREATE TABLE IF NOT EXISTS project.automation_rules (
    id SERIAL PRIMARY KEY,
    project_slug TEXT,
    workflow_type TEXT,
    deliverable_type TEXT,
    auto_approve BOOLEAN DEFAULT FALSE,
    confidence_threshold NUMERIC(3,2) DEFAULT 0.0,
    min_approved_history INTEGER DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (project_slug, workflow_type, deliverable_type)
);

-- Link existing tables to workflows
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='dispatcher_tasks' AND column_name='workflow_id') THEN
        ALTER TABLE project.dispatcher_tasks ADD COLUMN workflow_id INTEGER REFERENCES project.project_workflows(id);
        CREATE INDEX idx_disp_tasks_wf ON project.dispatcher_tasks(workflow_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='dispatcher_task_artifacts' AND column_name='workflow_id') THEN
        ALTER TABLE project.dispatcher_task_artifacts ADD COLUMN workflow_id INTEGER REFERENCES project.project_workflows(id);
        CREATE INDEX idx_disp_artifacts_wf ON project.dispatcher_task_artifacts(workflow_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='pm_issues' AND column_name='workflow_id') THEN
        ALTER TABLE project.pm_issues ADD COLUMN workflow_id INTEGER REFERENCES project.project_workflows(id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='project' AND table_name='hitl_requests' AND column_name='workflow_id') THEN
        ALTER TABLE project.hitl_requests ADD COLUMN workflow_id INTEGER REFERENCES project.project_workflows(id);
    END IF;
END $$;
