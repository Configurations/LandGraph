# Phase 3b Report — Pull Requests, Pulse, Workflow Visualization

Date: 2026-03-22

## 1. Inventaire fichiers

### Backend — Source (hitl-new/)

| Fichier | Lignes | Role |
|---|---|---|
| `schemas/pr.py` | 45 | Pydantic schemas PR (PRCreate, PRStatusUpdate, PRResponse) |
| `schemas/pulse.py` | 52 | Pydantic schemas Pulse (MetricValue, DependencyHealth, PulseResponse) |
| `schemas/workflow.py` | 47 | Pydantic schemas Workflow (PhaseAgent, PhaseDeliverable, PhaseStatus) |
| `services/pr_service.py` | 264 | PR CRUD, diff stats, merge (git operations) |
| `services/pr_remote.py` | 68 | Remote PR creation (GitHub/GitLab API) |
| `services/pulse_service.py` | 277 | Pulse metrics aggregation (status, velocity, burndown, etc.) |
| `services/workflow_service.py` | 234 | Workflow visualization (reads Workflow.json, resolves agent/deliverable statuses) |
| `routes/prs.py` | 79 | PR HTTP endpoints (CRUD + merge) |
| `routes/pulse.py` | 29 | Pulse HTTP endpoint |
| `routes/workflow.py` | 43 | Workflow HTTP endpoints |
| `routes/project_detail.py` | 149 | Project overview + team endpoints |
| **Total source** | **1287** | |

### Backend — Tests (hitl-new/tests/)

| Fichier | Lignes | Cas de test |
|---|---|---|
| `test_pr_service.py` | 165 | 5 tests: list (filtered + no filter), create (insert+log), update (status+notify), merge (approved), merge (not approved -> None) |
| `test_pulse_service.py` | 184 | 8 tests: status_distribution (2), velocity, throughput, cycle_time (2), dependency_health, burndown, get_pulse integration |
| `test_workflow_service.py` | 176 | 7 tests: get_workflow_status, get_phase_detail (found + not found), missing json, _determine_phase_status (4) |
| `test_pr_routes.py` | 135 | 5 tests: GET list 200, POST create 201, GET single 200 + 404, PUT update 200, POST merge 200 |
| `test_pulse_routes.py` | 65 | 2 tests: GET pulse 200, GET pulse with filters |
| `test_workflow_routes.py` | 82 | 3 tests: GET workflow 200, GET phase detail 200 + 404 |
| **Total backend tests** | **807** | **30 cas** |

### Frontend — Tests (hitl-frontend/tests/)

| Fichier | Lignes | Cas de test |
|---|---|---|
| `components/features/pm/PRRow.test.tsx` | 50 | 4 tests: title, issue_id, diff stats, status badges |
| `components/features/pm/PRActions.test.tsx` | 39 | 5 tests: review buttons (open + changes_requested), merge (approved), hide merge, hide all (merged) |
| `components/features/pm/PulseStatusBar.test.tsx` | 42 | 3 tests: segments per status, proportional widths, empty bar |
| `components/features/pm/PulseMetricCards.test.tsx` | 68 | 4 tests: 4 cards, values, label keys, subtitles |
| `components/features/workflow/WorkflowPhaseBar.test.tsx` | 55 | 5 tests: circles per phase, numbering, completed color, active color, onClick |
| `components/features/project/ProjectTabs.test.tsx` | 37 | 3 tests: 6 labels, active highlight, onTabChange |
| `components/features/project/DependencyGraphSimple.test.tsx` | 69 | 4 tests: SVG rendered, node IDs, edges with red stroke, empty message |
| `stores/prStore.test.ts` | 65 | 6 tests: initial state, loadPRs, setStatusFilter (2), setSelected (2) |
| **Total frontend tests** | **425** | **34 cas** |

### Total global

| Scope | Fichiers | Lignes | Cas |
|---|---|---|---|
| Backend tests | 6 | 807 | 30 |
| Frontend tests | 8 | 425 | 34 |
| **Total Phase 3b** | **14** | **1232** | **64** |

## 2. Ecarts spec

### pr_remote.py split

Le service PR a ete naturellement scinde en deux fichiers :
- `pr_service.py` (264 lignes) : CRUD, merge, diff stats
- `pr_remote.py` (68 lignes) : creation de PR distante via GitHub/GitLab API

Le test `test_pr_service.py` mocke `create_remote_pr` via patch, ce qui est coherent avec le split.

### pulse_service.py

Le service Pulse reste monolithique (277 lignes) avec des fonctions internes privees (`_status_distribution`, `_velocity`, etc.). Chaque sous-metrique est testee individuellement + un test d'integration pour `get_pulse`.

### Backend PR schema divergence

Le schema backend `PRResponse` utilise `files: int` tandis que le type frontend utilise `files_changed: int`. Les tests frontend utilisent le type frontend (`files_changed`).

## 3. Ecarts phases precedentes

Aucun ecart detecte. Les patterns de test (conftest, mock_pool, app_client, encode_token + AUTH headers) sont identiques aux phases 2 et 3a.

## 4. Schemas API reels

### PR

```
GET    /api/pm/reviews              -> list[PRResponse]   (query: project_slug?, status?)
POST   /api/pm/reviews              -> PRResponse (201)   (body: PRCreate)
GET    /api/pm/reviews/{pr_id}      -> PRResponse | 404
PUT    /api/pm/reviews/{pr_id}      -> PRResponse | 404   (body: PRStatusUpdate)
POST   /api/pm/reviews/{pr_id}/merge -> PRResponse | 404
```

### Pulse

```
GET    /api/pm/pulse                -> PulseResponse       (query: team_id?, project_id?)
```

### Workflow

```
GET    /api/projects/{slug}/workflow           -> WorkflowStatusResponse | 404
GET    /api/projects/{slug}/workflow/{phase_id} -> PhaseStatus | 404
```

### Project Detail

```
GET    /api/projects/{slug}/overview -> dict (issues, deliverables, costs, current_phase)
GET    /api/projects/{slug}/team     -> dict (members, agents)
```

## 5. Composants React reels

| Composant | Fichier | Props cles |
|---|---|---|
| `PRRow` | `pm/PRRow.tsx` (65L) | `pr: PRResponse, onClick` |
| `PRActions` | `pm/PRActions.tsx` (45L) | `status: PRStatus, onApprove, onRequestChanges, onMerge` |
| `PRDetail` | `pm/PRDetail.tsx` | (non teste — page composite) |
| `PRList` | `pm/PRList.tsx` | (non teste — page composite) |
| `PulseStatusBar` | `pm/PulseStatusBar.tsx` (62L) | `breakdown: Record<IssueStatus, number>` |
| `PulseMetricCards` | `pm/PulseMetricCards.tsx` (48L) | `velocity, throughput, cycleTime, burndownTotal: MetricValue` |
| `PulseTeamActivity` | `pm/PulseTeamActivity.tsx` | (non teste — table display) |
| `PulseDependencyHealth` | `pm/PulseDependencyHealth.tsx` | (non teste — metric display) |
| `PulseBurndownChart` | `pm/PulseBurndownChart.tsx` | (non teste — chart) |
| `WorkflowPhaseBar` | `workflow/WorkflowPhaseBar.tsx` (72L) | `phases: PhaseStatus[], selectedPhaseId, onSelectPhase` |
| `WorkflowPhaseDetail` | `workflow/WorkflowPhaseDetail.tsx` | (non teste — composite) |
| `WorkflowAgentCard` | `workflow/WorkflowAgentCard.tsx` | (non teste — card) |
| `WorkflowDeliverableRow` | `workflow/WorkflowDeliverableRow.tsx` | (non teste — row) |
| `ProjectTabs` | `project/ProjectTabs.tsx` (38L) | `activeTab: ProjectTab, onTabChange` |
| `DependencyGraphSimple` | `project/DependencyGraphSimple.tsx` (141L) | `issues, relations` |

## 6. Cles i18n nouvelles

```
pr.status_draft, pr.status_open, pr.status_approved,
pr.status_changes_requested, pr.status_merged, pr.status_closed
pr.approve, pr.request_changes, pr.merge
pr.files_count
time.just_now, time.minutes_ago, time.hours_ago, time.days_ago
pulse.velocity, pulse.throughput, pulse.cycle_time, pulse.burndown
issue.status_backlog, issue.status_todo, issue.status_in-progress,
issue.status_in-review, issue.status_done
workflow.phase_{id}
project_detail.tab_issues, project_detail.tab_deliverables,
project_detail.tab_workflow, project_detail.tab_activity,
project_detail.tab_team, project_detail.tab_dependencies
project_detail.no_dependencies, project_detail.dependency_graph
```

## 7. Tests etat

| Backend | Status |
|---|---|
| test_pr_service.py | Ecrit, 5 cas (mock fetch_one/fetch_all/execute) |
| test_pulse_service.py | Ecrit, 8 cas (mock fetch_one/fetch_all pour chaque metrique) |
| test_workflow_service.py | Ecrit, 7 cas (mock _read_workflow_json + agent/deliv status) |
| test_pr_routes.py | Ecrit, 5 cas (mock service layer, encode_token auth) |
| test_pulse_routes.py | Ecrit, 2 cas (mock get_pulse) |
| test_workflow_routes.py | Ecrit, 3 cas (mock get_workflow_status + get_phase_detail) |

| Frontend | Status |
|---|---|
| PRRow.test.tsx | Ecrit, 4 cas (render + status variants) |
| PRActions.test.tsx | Ecrit, 5 cas (conditional button visibility) |
| PulseStatusBar.test.tsx | Ecrit, 3 cas (segments + proportional widths) |
| PulseMetricCards.test.tsx | Ecrit, 4 cas (4 cards + values + labels) |
| WorkflowPhaseBar.test.tsx | Ecrit, 5 cas (circles + colors + click) |
| ProjectTabs.test.tsx | Ecrit, 3 cas (6 tabs + highlight + callback) |
| DependencyGraphSimple.test.tsx | Ecrit, 4 cas (SVG + nodes + edges + empty) |
| prStore.test.ts | Ecrit, 6 cas (state + loadPRs + filters + selection) |

Contrainte de 300 lignes max par fichier respectee : plus gros fichier = `test_pulse_service.py` a 184 lignes.

## 8. Modifications SQL

Aucune modification SQL dans cette phase de test. Les tables existantes sont :
- `project.pm_pull_requests` (PR CRUD)
- `project.pm_issues` (pulse metrics source)
- `project.pm_issue_relations` (dependency health)
- `project.dispatcher_tasks` / `project.dispatcher_task_artifacts` (workflow status)

## 9. Points Phase 4

1. **Multi-workflow** : supporter plusieurs Workflow.json par projet (A/B testing de pipelines)
2. **Types projet** : templates de workflow par type (SaaS, mobile, API, library)
3. **Automation progressive** : auto-merge quand CI passe + tous reviews approved
4. **Audit trail** : log immutable de toutes les transitions workflow + PR status changes
5. **Notifications push** : WebSocket events pour PR status changes + phase transitions
6. **Cost tracking** : integrer les couts LLM dans le pulse dashboard

## 10. Commandes

```bash
# Backend tests
cd hitl-new
python -m pytest tests/test_pr_service.py tests/test_pulse_service.py tests/test_workflow_service.py tests/test_pr_routes.py tests/test_pulse_routes.py tests/test_workflow_routes.py -v

# Frontend tests
cd hitl-frontend
npx vitest run tests/components/features/pm/PRRow.test.tsx tests/components/features/pm/PRActions.test.tsx tests/components/features/pm/PulseStatusBar.test.tsx tests/components/features/pm/PulseMetricCards.test.tsx tests/components/features/workflow/WorkflowPhaseBar.test.tsx tests/components/features/project/ProjectTabs.test.tsx tests/components/features/project/DependencyGraphSimple.test.tsx tests/stores/prStore.test.ts

# All Phase 3b tests
cd hitl-new && python -m pytest tests/test_pr_service.py tests/test_pulse_service.py tests/test_workflow_service.py tests/test_pr_routes.py tests/test_pulse_routes.py tests/test_workflow_routes.py -v
cd hitl-frontend && npx vitest run --reporter=verbose
```
