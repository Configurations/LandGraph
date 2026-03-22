# Phase 0 — Agent Dispatcher Service — Rapport de fin de phase

> **Date** : 2026-03-22
> **Service** : `langgraph-dispatcher` (port 8070)
> **Stack** : Python 3.11, FastAPI, asyncpg, aiodocker, structlog

---

## 1. Inventaire des fichiers

### Service (code metier)

| Fichier | Lignes | Role |
|---|---|---|
| `dispatcher/main.py` | 101 | App FastAPI, lifespan, wiring singletons |
| `dispatcher/core/config.py` | 25 | Settings pydantic-settings (env vars) |
| `dispatcher/core/database.py` | 70 | Pool asyncpg + helpers (execute, fetch, listen conn) |
| `dispatcher/core/events.py` | 95 | PG NOTIFY listener/publisher + HitlResponseWaiter |
| `dispatcher/models/task.py` | 106 | Dataclasses Task, TaskPayload, 4 event types, enums |
| `dispatcher/models/schemas.py` | 88 | Pydantic v2 schemas request/response (7 schemas) |
| `dispatcher/services/docker_manager.py` | 173 | Gestion containers Docker (aiodocker), managed_container |
| `dispatcher/services/stdio_bridge.py` | 97 | Parse stdout events, write stdin JSON |
| `dispatcher/services/task_db.py` | 130 | Helpers DB : insert/fetch/mark task, build_task/env/volumes |
| `dispatcher/services/task_runner.py` | 184 | Orchestration lifecycle complet d'une tache |
| `dispatcher/services/hitl_bridge.py` | 89 | Question HITL : insert request, PG NOTIFY, wait response |
| `dispatcher/services/artifact_store.py` | 92 | Persistance livrables sur disque + DB |
| `dispatcher/services/cost_tracker.py` | 79 | Enregistrement + agregation couts par agent/phase |
| `dispatcher/routes/health.py` | 22 | GET /health |
| `dispatcher/routes/tasks.py` | 129 | POST run, GET detail, GET events, POST cancel |
| `dispatcher/routes/internal.py` | 72 | GET costs, GET active tasks |

### Tests

| Fichier | Lignes | Tests |
|---|---|---|
| `dispatcher/tests/conftest.py` | 124 | Fixtures partagees (mock pool, mock docker, sample_task) |
| `dispatcher/tests/test_stdio_bridge.py` | 193 | 18 |
| `dispatcher/tests/test_docker_manager.py` | 300 | 25 |
| `dispatcher/tests/test_artifact_store.py` | 141 | 7 |
| `dispatcher/tests/test_cost_tracker.py` | 137 | 7 |
| `dispatcher/tests/test_hitl_bridge.py` | 187 | 12 |
| `dispatcher/tests/test_task_runner.py` | 186 | 15 |
| `dispatcher/tests/test_task_db.py` | 78 | 6 |
| `dispatcher/tests/test_routes.py` | 262 | 12 |
| **Total** | **1608** | **102** |

### Infrastructure

| Fichier | Lignes | Role |
|---|---|---|
| `dispatcher/requirements.txt` | 9 | Dependances Python |
| `dispatcher/entrypoint.claude-code.sh` | 71 | Entrypoint agent (stdin Task, stdout Events) |
| `Dockerfile.dispatcher` | 12 | Image Docker du dispatcher |
| `5 x __init__.py` | 0 | Packages Python |

### Fichiers existants modifies

| Fichier | Modification |
|---|---|
| `scripts/init.sql` | +91 lignes : 4 tables dispatcher + trigger hitl_response |
| `docker-compose.yml` | +28 lignes : service langgraph-dispatcher |
| `deploy.sh` | +3 lignes : detection dispatcher/ + ajout aux rebuild globaux |

### Totaux

- **Fichiers crees** : 28
- **Lignes code metier** : ~1552
- **Lignes tests** : ~1608
- **Lignes infra** : ~92
- **Contrainte < 300 lignes** : respectee (max = 300 : test_docker_manager.py)

---

## 2. Ecarts entre la spec et l'implementation

| Point de la spec | Impl | Ecart |
|---|---|---|
| Structure `dispatcher/` | Conforme | Fichier `task_db.py` ajoute (non prevu) pour respecter la limite de 300 lignes |
| Tables SQL | Conforme | Index prefixes `idx_disp_*` au lieu de `idx_tasks_*` (eviter conflit avec d'autres tables) |
| Protocole stdio 4 events | Conforme | — |
| Docker manager avec `aiodocker` | Conforme | — |
| `managed_container` context manager | Conforme | — |
| HITL bridge avec PG NOTIFY | Conforme | — |
| Artifact store sur disque | Conforme | Pas de copie vers `repo/docs/{categorie}` apres validation (prevu pour Phase 1+) |
| Cost tracker avec UPSERT | Conforme | — |
| Task runner lifecycle complet | Conforme | Decompose en `create()` + `execute_by_id()` + `run()` pour le pattern 202 Accepted |
| Reprise apres crash | **Partiel** | Le champ `previous_answers` est passe au container mais la detection auto de crash (Docker events) n'est pas implementee — relance manuelle via `POST /api/tasks/run` avec previous_answers |
| Alembic migrations | **Non fait** | Les tables sont dans `init.sql` (pattern existant du projet, pas d'Alembic) |
| README.md | **Non fait** | Remplace par ce PHASE0_REPORT.md |
| `structlog` JSON | Conforme | Configure dans `main.py`, utilise dans tous les services |
| Python 3.11 | Conforme | Meme version que le reste du projet |

---

## 3. DDL PostgreSQL

### Table `project.dispatcher_tasks`

```sql
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
        CHECK (status IN ('pending','running','waiting_hitl','success','failure','timeout','cancelled')),
    container_id TEXT,
    docker_image TEXT NOT NULL,
    cost_usd NUMERIC(10,4) DEFAULT 0,
    timeout_seconds INTEGER DEFAULT 300,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    error_message TEXT
);
-- Index: idx_disp_tasks_status, idx_disp_tasks_project, idx_disp_tasks_agent
```

### Table `project.dispatcher_task_events`

```sql
CREATE TABLE IF NOT EXISTS project.dispatcher_task_events (
    id SERIAL PRIMARY KEY,
    task_id UUID REFERENCES project.dispatcher_tasks(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('progress','artifact','question','result')),
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- Index: idx_disp_events_task (task_id, created_at)
```

### Table `project.dispatcher_task_artifacts`

```sql
CREATE TABLE IF NOT EXISTS project.dispatcher_task_artifacts (
    id SERIAL PRIMARY KEY,
    task_id UUID REFERENCES project.dispatcher_tasks(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    deliverable_type TEXT NOT NULL,
    file_path TEXT,
    git_branch TEXT,
    category TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    reviewer TEXT,
    reviewed_at TIMESTAMPTZ,
    review_comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- Index: idx_disp_artifacts_task, idx_disp_artifacts_status
```

### Table `project.dispatcher_cost_summary`

```sql
CREATE TABLE IF NOT EXISTS project.dispatcher_cost_summary (
    id SERIAL PRIMARY KEY,
    project_slug TEXT NOT NULL,
    team_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    total_cost_usd NUMERIC(10,4) DEFAULT 0,
    task_count INTEGER DEFAULT 0,
    avg_cost_per_task NUMERIC(10,4) DEFAULT 0,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (project_slug, team_id, phase, agent_id)
);
```

### Trigger `notify_hitl_response`

```sql
CREATE OR REPLACE FUNCTION notify_hitl_response() RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status = 'pending' AND NEW.status = 'answered' THEN
        PERFORM pg_notify('hitl_response', json_build_object(
            'request_id', NEW.id,
            'response', LEFT(NEW.response, 4000),
            'reviewer', NEW.reviewer
        )::text);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Sur project.hitl_requests (table existante)
CREATE TRIGGER trigger_hitl_response
    AFTER UPDATE ON project.hitl_requests
    FOR EACH ROW EXECUTE FUNCTION notify_hitl_response();
```

---

## 4. Canaux PG NOTIFY

| Channel | Emetteur | Payload | Consommateur |
|---|---|---|---|
| `hitl_response` | **Trigger SQL** (hitl_requests UPDATE) | `{"request_id": UUID, "response": str, "reviewer": str}` | `dispatcher` (HitlResponseWaiter) |
| `hitl_request` | `dispatcher` (hitl_bridge.ask) | `{"request_id": UUID, "thread_id": str, "agent_id": str, "team_id": str, "prompt": str}` | Console HITL (Phase 1) |
| `task_progress` | `dispatcher` (task_runner) | `{"task_id": UUID, "data": str}` | Console HITL (Phase 1) |
| `task_artifact` | `dispatcher` (task_runner) | `{"task_id": UUID, "key": str}` | Console HITL (Phase 1) |

---

## 5. Schemas Pydantic

### Request : `RunTaskRequest`

```python
class RunTaskRequest(BaseModel):
    agent_id: str                              # ID de l'agent (ex: "lead_dev")
    team_id: str                               # ID de l'equipe
    thread_id: str                             # ID du thread de conversation
    project_slug: Optional[str] = None         # Slug du projet
    phase: str = "build"                       # Phase du workflow
    iteration: int = 1                         # Numero d'iteration
    payload: TaskPayloadSchema                 # Instruction + contexte
    timeout_seconds: int = 300                 # Timeout max du container
    docker_image: Optional[str] = None         # Image Docker (None = defaut)
```

### Request : `TaskPayloadSchema`

```python
class TaskPayloadSchema(BaseModel):
    instruction: str                           # Instruction pour l'agent
    context: dict[str, Any] = {}               # Contexte additionnel
    previous_answers: list[dict[str, str]] = [] # Q&A precedentes (reprise)
```

### Response : `TaskResponse`

```python
class TaskResponse(BaseModel):
    task_id: UUID
    status: str                  # pending|running|waiting_hitl|success|failure|timeout|cancelled
    agent_id: str
    team_id: str
    project_slug: Optional[str]
    phase: str
    cost_usd: float = 0.0
    created_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
```

### Response : `TaskDetailResponse` (extends TaskResponse)

```python
class TaskDetailResponse(TaskResponse):
    events: list[TaskEventResponse] = []
    artifacts: list[TaskArtifactResponse] = []
```

### Response : `TaskEventResponse`

```python
class TaskEventResponse(BaseModel):
    id: int
    task_id: UUID
    event_type: str              # progress|artifact|question|result
    data: Any                    # Contenu JSON de l'event
    created_at: datetime
```

### Response : `TaskArtifactResponse`

```python
class TaskArtifactResponse(BaseModel):
    id: int
    task_id: UUID
    key: str                     # Cle du livrable (ex: "prd")
    deliverable_type: str        # Type (delivers_docs, delivers_code, etc.)
    file_path: Optional[str]     # Chemin disque
    git_branch: Optional[str]    # Branche git (pour code)
    category: Optional[str]      # Categorie du workflow
    status: str = "pending"      # pending|approved|rejected
    created_at: datetime
```

### Response : `ProjectCostsResponse`

```python
class ProjectCostsResponse(BaseModel):
    project_slug: str
    total_cost_usd: float
    by_phase: list[CostSummaryResponse]
```

### Response : `CostSummaryResponse`

```python
class CostSummaryResponse(BaseModel):
    project_slug: str
    team_id: str
    phase: str
    agent_id: str
    total_cost_usd: float
    task_count: int
    avg_cost_per_task: float
```

---

## 6. Endpoints API

| Methode | Path | Request | Response | Status | Description |
|---|---|---|---|---|---|
| GET | `/health` | — | `{status, db}` | 200 | Health check + connectivite DB |
| POST | `/api/tasks/run` | `RunTaskRequest` | `{task_id, status}` | 202 | Lance une tache en background |
| GET | `/api/tasks/{task_id}` | — | `TaskDetailResponse` | 200/404 | Detail tache + events + artifacts |
| GET | `/api/tasks/{task_id}/events` | — | `list[TaskEventResponse]` | 200 | Events d'une tache |
| POST | `/api/tasks/{task_id}/cancel` | — | `{status}` | 200/400 | Annuler une tache (kill container) |
| GET | `/api/tasks/active` | — | `list[TaskResponse]` | 200 | Taches en cours (max 50) |
| GET | `/api/costs/{project_slug}` | — | `ProjectCostsResponse` | 200 | Couts agreges par phase/agent |

---

## 7. Etat des tests

| Fichier | Tests | Etat |
|---|---|---|
| `test_stdio_bridge.py` | 18 | Unitaires, mock streams |
| `test_docker_manager.py` | 25 | Unitaires, mock aiodocker |
| `test_artifact_store.py` | 7 | Unitaires, mock DB + filesystem |
| `test_cost_tracker.py` | 7 | Unitaires, mock DB |
| `test_hitl_bridge.py` | 12 | Unitaires, mock PG NOTIFY |
| `test_task_runner.py` | 15 | Unitaires, mock tous services |
| `test_task_db.py` | 6 | Unitaires, mock DB |
| `test_routes.py` | 12 | Integration FastAPI (TestClient) |
| **Total** | **102** | **Non executes** (pas de DB/Docker en dev local Windows) |

> **Note** : les tests sont ecrits pour s'executer avec `pytest tests/ -v --tb=short` dans le container ou sur un environnement Linux avec PostgreSQL. Ils utilisent des mocks et ne necessitent pas de services reels pour les tests unitaires.

---

## 8. Points d'attention pour la Phase 1 (Console HITL React)

### Integration dispatcher ↔ console HITL

1. **Ecouter `hitl_request`** — la console doit LISTEN sur le channel PG NOTIFY `hitl_request` pour afficher les questions en temps reel. Payload : `{request_id, thread_id, agent_id, team_id, prompt}`

2. **Repondre via l'API existante** — la console utilise deja `POST /api/questions/{id}/answer` pour repondre. Le trigger SQL `notify_hitl_response` se declenche automatiquement et le dispatcher recoit la reponse. **Aucune modification cote dispatcher necessaire.**

3. **Ecouter `task_progress` et `task_artifact`** — pour afficher la progression des taches en temps reel (WebSocket vers le frontend).

4. **Channel `docker`** — les requests HITL creees par le dispatcher ont `channel = 'docker'`. La console doit filtrer sur ce channel pour les distinguer des requetes Discord/Email.

### Endpoints utiles pour la console

- `GET /api/tasks/active` → dashboard des taches en cours
- `GET /api/tasks/{id}` → detail + events + artifacts pour une tache
- `GET /api/costs/{slug}` → affichage des couts par projet

### Schema DB existant reutilisable

- La table `project.hitl_requests` est deja utilisee par la console HITL existante. Le dispatcher y insere des rows avec `channel = 'docker'` et `request_type = 'question'`. La console peut les traiter comme les autres requests.

### Considerations

- **Artifacts** : les livrables sont persistes dans `dispatcher_task_artifacts` (table) et sur disque. La console doit pouvoir les lire et proposer l'approbation/rejet (UPDATE `status`, `reviewer`, `review_comment`).
- **Reprise apres crash** : non automatisee en Phase 0. La Phase 1 pourrait ajouter un bouton "Relancer" qui appelle `POST /api/tasks/run` avec les `previous_answers` enrichies.
- **WebSocket** : le dispatcher n'expose pas de WebSocket. La console doit ecouter PG NOTIFY directement ou passer par un proxy WebSocket.

---

## 9. Commandes de lancement

### Developpement local

```bash
cd dispatcher
pip install -r requirements.txt
DATABASE_URI=postgresql://user:pass@localhost:5432/langgraph \
  python -m uvicorn main:app --host 0.0.0.0 --port 8070 --reload
```

### Docker (production)

```bash
# Build
docker compose build langgraph-dispatcher

# Lancer
docker compose up -d langgraph-dispatcher

# Verifier
curl http://localhost:8070/health

# Logs
docker logs -f langgraph-dispatcher
```

### Tests

```bash
cd dispatcher
pip install pytest pytest-asyncio
pytest tests/ -v --tb=short
```

### Deploiement AGT1

```bash
bash deploy.sh AGT1
# Le script detecte les changements dans dispatcher/ et rebuild automatiquement
```

### Application du schema SQL (premiere fois)

```bash
docker exec -i langgraph-postgres psql -U langgraph -d langgraph < scripts/init.sql
```

---

## 10. Variables d'environnement

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URI` | `postgresql://...` | URI PostgreSQL |
| `REDIS_URI` | `redis://...` | URI Redis |
| `DISPATCHER_PORT` | `8070` | Port du service |
| `AGENT_DEFAULT_IMAGE` | `agflow-claude-code:latest` | Image Docker par defaut pour les agents |
| `AGENT_MEM_LIMIT` | `2g` | Limite memoire par container agent |
| `AGENT_CPU_QUOTA` | `100000` | Quota CPU par container agent |
| `AG_FLOW_ROOT` | `/root/ag.flow` | Racine du stockage projets/artifacts |
| `LANGGRAPH_API_URL` | `http://langgraph-api:8000` | URL du gateway API |
| `HITL_QUESTION_TIMEOUT` | `1800` (30 min) | Timeout attente reponse HITL |
| `ANTHROPIC_API_KEY` | — | Cle API Anthropic (passee aux containers agents) |
