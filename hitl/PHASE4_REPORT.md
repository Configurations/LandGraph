# Phase 4 Report — Multi-Workflow, Project Types, Automation

Date: 2026-03-22

---

## 1. Inventaire des fichiers

### Backend (hitl-new/tests/)

| Fichier | Lignes | Tests |
|---|---|---|
| `test_multi_workflow_service.py` | 208 | 9 |
| `test_project_type_service.py` | 131 | 4 |
| `test_automation_service.py` | 196 | 8 |
| `test_workflow_routes_multi.py` | 150 | 8 |
| `test_project_type_routes.py` | 104 | 5 |
| `test_automation_routes.py` | 129 | 6 |
| **Sous-total backend** | **918** | **40** |

### Frontend (hitl-frontend/tests/components/features/)

| Fichier | Lignes | Tests |
|---|---|---|
| `project/WorkflowSelector.test.tsx` | 38 | 4 |
| `project/WorkflowCard.test.tsx` | 64 | 4 |
| `project/ProjectTypeSelector.test.tsx` | 46 | 3 |
| `automation/AutomationRuleList.test.tsx` | 51 | 4 |
| `automation/AutomationStats.test.tsx` | 33 | 3 |
| **Sous-total frontend** | **232** | **18** |

| | Fichiers | Lignes | Tests |
|---|---|---|---|
| **Total** | **11** | **1150** | **58** |

Aucun fichier ne depasse 300 lignes. Le plus long est `test_multi_workflow_service.py` (208 lignes).

---

## 2. Ecarts spec

| Spec | Impl | Ecart |
|---|---|---|
| `test_multi_workflow_service.py` ~180 lignes, 8 tests | 208 lignes, 9 tests | +1 test (`relaunch_returns_none_for_active`) |
| `test_project_type_service.py` ~100 lignes, 4 tests | 131 lignes, 4 tests | Lignes supplementaires dues aux fixtures Pydantic |
| `test_automation_service.py` ~150 lignes, 7 tests | 196 lignes, 8 tests | +1 test (`get_agent_confidence_zero_history`) |
| `test_workflow_routes_multi.py` ~120 lignes, 4 tests spec | 150 lignes, 8 tests | +4 tests (pause, complete, relaunch, 404) |
| `test_project_type_routes.py` ~80 lignes, 3 tests | 104 lignes, 5 tests | +2 tests (404 cases) |
| `test_automation_routes.py` ~80 lignes, 6 tests | 129 lignes, 6 tests | Conforme |
| Frontend 5 fichiers | 5 fichiers | Conforme |

---

## 3. Ecarts phases precedentes

Aucun ecart. Les tests Phase 4 suivent les memes conventions que les phases 1-3 :

- **Backend** : `pytest` + `pytest-asyncio`, `patch()` sur les fonctions `fetch_one`/`fetch_all`/`execute`, `FakeRecord` de `conftest.py`, `encode_token` pour l'auth JWT
- **Frontend** : `vitest` + `@testing-library/react`, mock `react-i18next` via `setup.ts`, imports relatifs `../../../../src/...`

Les schemas existants (`schemas/workflow.py`, `schemas/automation.py`, `schemas/project_type.py`) ont ete reutilises sans modification.

---

## 4. Schemas API

### Multi-Workflow (`/api/projects/{slug}/workflows`)

| Methode | Endpoint | Status | Body / Response |
|---|---|---|---|
| GET | `/{slug}/workflows` | 200 | `ProjectWorkflowResponse[]` |
| POST | `/{slug}/workflows` | 201 | `ProjectWorkflowCreate` -> `ProjectWorkflowResponse` |
| GET | `/{slug}/workflows/{id}` | 200/404 | `ProjectWorkflowResponse` |
| POST | `/{slug}/workflows/{id}/activate` | 200/409 | `ProjectWorkflowResponse` |
| POST | `/{slug}/workflows/{id}/pause` | 200/409 | `ProjectWorkflowResponse` |
| POST | `/{slug}/workflows/{id}/complete` | 200/409 | `ProjectWorkflowResponse` |
| POST | `/{slug}/workflows/{id}/cancel` | 200/409 | `ProjectWorkflowResponse` |
| POST | `/{slug}/workflows/{id}/relaunch` | 200/409 | `ProjectWorkflowResponse` |

```
ProjectWorkflowCreate {
  workflow_name: str
  workflow_type: str = "custom"
  workflow_json_path: str
  mode: str = "sequential"
  priority: int = 50
  depends_on_workflow_id: int?
  config: dict = {}
}

ProjectWorkflowResponse {
  id: int
  project_slug: str
  workflow_name, workflow_type, workflow_json_path: str
  status: str  (pending|active|paused|completed|cancelled)
  mode: str
  priority: int
  iteration: int
  depends_on_workflow_id: int?
  config: dict
  started_at, completed_at, created_at: str?
}
```

### Project Types (`/api/project-types`)

| Methode | Endpoint | Status | Response |
|---|---|---|---|
| GET | `/api/project-types` | 200 | `ProjectTypeResponse[]` |
| GET | `/api/project-types/{id}` | 200/404 | `ProjectTypeResponse` |
| POST | `/api/projects/{slug}/apply-type/{id}` | 200/404 | `{ok, workflow_ids}` |

```
ProjectTypeResponse {
  id, name, description, team: str
  workflows: WorkflowTemplate[]
}

WorkflowTemplate {
  name, filename: str
  type: str = "custom"
  mode: str = "sequential"
  priority: int = 50
  depends_on: str?
}
```

### Automation (`/api/automation`)

| Methode | Endpoint | Status | Response |
|---|---|---|---|
| GET | `/rules` | 200 | `AutomationRuleResponse[]` |
| POST | `/rules` | 201 | `AutomationRuleResponse` |
| PUT | `/rules/{id}` | 200/404 | `AutomationRuleResponse` |
| DELETE | `/rules/{id}` | 200/404 | `{ok}` |
| GET | `/stats?project_slug=` | 200 | `AutomationStatsResponse` |
| GET | `/agent-confidence/{id}` | 200 | `AgentConfidenceResponse` |

```
AutomationStatsResponse {
  total_reviewed, auto_approved, manual_approved, rejected: int
  auto_pct, manual_pct, rejected_pct: float
}

AgentConfidenceResponse {
  agent_id: str
  deliverable_type: str
  total, approved, rejected: int
  confidence: float
}
```

---

## 5. Composants React

| Composant | Props | Teste |
|---|---|---|
| `WorkflowSelector` | `workflows: ProjectWorkflowResponse[], selectedId, onSelect` | Rendu tabs, highlight, onSelect, empty |
| `WorkflowCard` | `workflow: ProjectWorkflowResponse, onActivate?, onPause?, onComplete?, onRelaunch?` | Badges, boutons par status, callbacks |
| `ProjectTypeSelector` | `teamId, selectedTypeId, onSelect` | Chargement async, cards, highlight, skip |
| `ProjectTypeCard` | `projectType: ProjectTypeResponse, selected, onSelect` | (teste indirectement via ProjectTypeSelector) |
| `AutomationRuleList` | `rules: AutomationRule[], onToggle, onEdit, onDelete, onAdd` | Table, toggle, empty state, add |
| `AutomationStats` | `stats: AutomationStats` | 3 segments, pourcentages, barres couleur |

---

## 6. Cles i18n

### Multi-Workflow

- `multi_workflow.no_workflows`
- `multi_workflow.status_draft`, `multi_workflow.status_active`, `multi_workflow.status_paused`, `multi_workflow.status_completed`
- `multi_workflow.mode_sequential`, `multi_workflow.mode_parallel`
- `multi_workflow.activate`, `multi_workflow.pause`, `multi_workflow.complete`, `multi_workflow.relaunch`
- `multi_workflow.progress_label`

### Project Types

- `project_type.no_types`, `project_type.skip`, `project_type.select_type`
- `project_type.workflows_count`

### Automation

- `automation.rules_title`, `automation.add_rule`, `automation.no_rules`
- `automation.toggle_rule`, `automation.edit`
- `automation.auto_approve`, `automation.threshold_label`, `automation.min_history_label`
- `automation.stats_title`, `automation.auto_approved`, `automation.manual_reviewed`, `automation.rejected`
- `automation.total_decisions`

### Common

- `common.delete`

---

## 7. Tests

### Strategie de test

- **Services** : mock `fetch_one`/`fetch_all`/`execute` via `unittest.mock.patch`, `FakeRecord` pour simuler les rows asyncpg
- **Routes** : mock le service entier, `app_client` fixture avec pool mocke, JWT via `encode_token`
- **Frontend** : `vi.mock` pour les API calls async, `@testing-library/react` pour le rendu, `vi.fn()` pour les callbacks

### Couverture

| Module | Fonctions testees |
|---|---|
| `multi_workflow_service` | create, activate (ok + fail), complete, check_transitions, relaunch (ok + fail), list, get_active |
| `project_type_service` | list_types, get_type (ok + missing), apply_type |
| `automation_service` | check_auto_approve (ok + below + no_rule), get_confidence (ok + zero), list_rules, create_rule, get_stats |
| `routes/workflows` | GET list, POST create, GET single + 404, POST activate/pause/complete/relaunch |
| `routes/project_types` | GET list, GET single + 404, POST apply + 404 |
| `routes/automation` | GET rules, POST rule, PUT rule, DELETE rule, GET stats, GET confidence |
| `WorkflowSelector` | tabs, highlight, onSelect, empty |
| `WorkflowCard` | badges, draft/active/completed buttons |
| `ProjectTypeSelector` | async load, cards, skip |
| `AutomationRuleList` | table, toggle, empty, add |
| `AutomationStats` | segments, percentages, colors |

---

## 8. Modifications dispatcher

Aucune modification du dispatcher existant. Les services Phase 4 sont additifs :

- `multi_workflow_service.py` : CRUD + lifecycle sur la table `project.project_workflows`
- `project_type_service.py` : lecture filesystem `Shared/Projects/` + appel a `create_workflow`
- `automation_service.py` : regles auto-approve sur `project.automation_rules` + jointure `dispatcher_task_artifacts`

Le point d'integration futur est `check_auto_approve()` qui devra etre appele par le dispatcher lorsqu'un artifact est soumis, avant de creer la question HITL.

---

## 9. Modifications SQL

### Tables requises (non creees par les tests, declaratives)

```sql
-- project.project_workflows
CREATE TABLE project.project_workflows (
    id              SERIAL PRIMARY KEY,
    project_slug    TEXT NOT NULL,
    workflow_name   TEXT NOT NULL,
    workflow_type   TEXT DEFAULT 'custom',
    workflow_json_path TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    mode            TEXT DEFAULT 'sequential',
    priority        INT DEFAULT 50,
    iteration       INT DEFAULT 1,
    depends_on_workflow_id INT REFERENCES project.project_workflows(id),
    config          JSONB DEFAULT '{}',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- project.automation_rules
CREATE TABLE project.automation_rules (
    id                    SERIAL PRIMARY KEY,
    project_slug          TEXT,
    workflow_type         TEXT,
    deliverable_type      TEXT,
    auto_approve          BOOLEAN DEFAULT false,
    confidence_threshold  NUMERIC DEFAULT 0,
    min_approved_history  INT DEFAULT 5,
    created_at            TIMESTAMPTZ DEFAULT now()
);
```

### Colonnes lues sur tables existantes

- `project.dispatcher_task_artifacts` : `id, task_id, deliverable_type, status, reviewer`
- `project.dispatcher_tasks` : `id, agent_id, project_slug, workflow_id`

---

## 10. Points pour la suite

### Mobile Flutter

- Les endpoints multi-workflow et automation sont REST standard, consommables directement depuis Flutter via `dio` ou `http`
- Les schemas Pydantic peuvent etre transposes en classes Dart via codegen (ex: `json_serializable`)

### Scaling

- `check_workflow_transitions` effectue une requete par projet ; si le nombre de workflows croit, un index composite `(project_slug, status)` sera necessaire
- `get_agent_confidence` fait un COUNT sur `dispatcher_task_artifacts` ; prevoir une table de cache si le volume depasse 100k artifacts par agent

### Optimisation

- `project_type_service` lit le filesystem a chaque appel ; un cache en memoire avec invalidation par inotify ou TTL 60s reduirait la latence
- `_find_matching_rule` effectue jusqu'a 3 requetes sequentielles ; un seul SELECT avec `ORDER BY specificity DESC LIMIT 1` serait plus performant

---

## 11. Commandes

### Backend

```bash
# Lancer tous les tests Phase 4
cd hitl-new
python -m pytest tests/test_multi_workflow_service.py tests/test_project_type_service.py tests/test_automation_service.py tests/test_workflow_routes_multi.py tests/test_project_type_routes.py tests/test_automation_routes.py -v

# Lancer un fichier specifique
python -m pytest tests/test_automation_service.py -v

# Lancer avec couverture
python -m pytest tests/test_multi_workflow_service.py tests/test_project_type_service.py tests/test_automation_service.py tests/test_workflow_routes_multi.py tests/test_project_type_routes.py tests/test_automation_routes.py --cov=services --cov=routes --cov-report=term-missing
```

### Frontend

```bash
# Lancer tous les tests Phase 4
cd hitl-frontend
npx vitest run tests/components/features/project/WorkflowSelector.test.tsx tests/components/features/project/WorkflowCard.test.tsx tests/components/features/project/ProjectTypeSelector.test.tsx tests/components/features/automation/AutomationRuleList.test.tsx tests/components/features/automation/AutomationStats.test.tsx

# Lancer un fichier specifique
npx vitest run tests/components/features/automation/AutomationStats.test.tsx

# Mode watch
npx vitest tests/components/features/automation/
```

### Tous les tests du projet

```bash
# Backend complet
cd hitl-new && python -m pytest tests/ -v

# Frontend complet
cd hitl-frontend && npx vitest run
```
