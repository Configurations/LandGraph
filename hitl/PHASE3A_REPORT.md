# Phase 3a Report — Production Manager (Issues, Relations, Inbox, Activity)

## 1. Inventaire fichiers

### Backend (hitl-new/) — Fichiers nouveaux

| Fichier | Lignes | Role |
|---|---|---|
| `schemas/issue.py` | 83 | Pydantic v2 schemas (IssueCreate, IssueUpdate, IssueResponse, IssueDetail, IssueBulkCreate, RelationResponse) |
| `schemas/relation.py` | 21 | Pydantic v2 schemas (RelationCreate, RelationBulkCreate) |
| `schemas/inbox.py` | 42 | Pydantic v2 schemas (NotificationResponse, ActivityEntry, MergedActivityResponse) |
| `services/issue_service.py` | 297 | CRUD issues, bulk create, search, blocking logic, auto-generated IDs |
| `services/issue_helpers.py` | 140 | row_to_response, fetch_issue_response, log_activity, notify_on_update, check_unblock_cascade |
| `services/relation_service.py` | 216 | CRUD relations, inverse type mapping, blocking notifications, bulk create |
| `services/inbox_service.py` | 99 | Notifications CRUD, mark read, unread count |
| `services/activity_service.py` | 122 | Activity log, merged PM + agent timeline |
| `routes/issues.py` | 112 | REST endpoints: GET/POST/PUT/DELETE /api/pm/issues, search, bulk |
| `routes/relations.py` | 66 | REST endpoints: GET/POST/DELETE /api/pm/issues/{id}/relations |
| `routes/inbox.py` | 53 | REST endpoints: GET/PUT /api/pm/inbox |
| `routes/activity.py` | 32 | REST endpoint: GET /api/pm/projects/{id}/activity |
| **Sous-total backend** | **1283** | |

### Backend (hitl-new/tests/) — Fichiers tests nouveaux

| Fichier | Lignes | Tests |
|---|---|---|
| `tests/test_issue_service.py` | 274 | 12 tests (create, update, list, delete, search, blocked, bulk) |
| `tests/test_relation_service.py` | 159 | 7 tests (create, self-ref, list, delete, unblock, not-found, bulk) |
| `tests/test_inbox_service.py` | 104 | 6 tests (list, mark_read, mark_all, unread_count, create) |
| `tests/test_activity_service.py` | 98 | 4 tests (log, list, merged, no-slug) |
| `tests/test_issue_routes.py` | 145 | 8 tests (POST 201, GET list, GET detail, 404, PUT, DELETE 204/404, search) |
| `tests/test_relation_routes.py` | 92 | 5 tests (POST 201, self-ref 400, GET list, DELETE 204/404) |
| `tests/test_inbox_routes.py` | 82 | 5 tests (GET list, PUT read, 404, read-all, count) |
| **Sous-total tests backend** | **954** | **47 tests** |

### Frontend (hitl-frontend/src/) — Fichiers nouveaux

| Fichier | Lignes | Role |
|---|---|---|
| `api/issues.ts` | 69 | API client issues (list, create, update, delete, search, bulk) |
| `api/relations.ts` | 34 | API client relations |
| `api/inbox.ts` | 23 | API client inbox |
| `api/activity.ts` | 12 | API client activity |
| `stores/issueStore.ts` | 53 | Zustand store (issues, filters, groupBy, selectedId) |
| `stores/inboxStore.ts` | 57 | Zustand store (notifications, unread count) |
| `components/features/pm/IssueRow.tsx` | 78 | Row component: ID, priority, status, blocked, tags, avatar |
| `components/features/pm/IssueList.tsx` | 108 | Grouped issue list with status/team/assignee/dependency grouping |
| `components/features/pm/IssueDetail.tsx` | 138 | Detail panel: fields, description, relations, delete |
| `components/features/pm/IssueCreateModal.tsx` | 104 | Create form: title, desc, priority, status, assignee, tags |
| `components/features/pm/IssueStatusIcon.tsx` | 58 | SVG icons for 5 statuses (backlog, todo, in-progress, in-review, done) |
| `components/features/pm/PriorityBadge.tsx` | 38 | 4-bar priority indicator (P1 red, P2 orange, P3 yellow, P4 gray) |
| `components/features/pm/BlockedBanner.tsx` | 42 | Red banner showing blocking issues |
| `components/features/pm/RelationList.tsx` | 73 | Relation list with directional display types |
| `components/features/pm/AddRelationModal.tsx` | 91 | Modal to add a relation with type picker and issue search |
| `components/features/pm/InboxBadge.tsx` | 22 | Unread count badge for sidebar |
| `components/features/pm/InboxList.tsx` | 75 | Full notification list with mark-all-read |
| `components/features/pm/InboxRow.tsx` | 64 | Single notification row with unread dot, text, issue link |
| `components/features/pm/ActivityEntryRow.tsx` | 59 | Single activity entry (PM or agent source) |
| `components/features/pm/ActivityTimeline.tsx` | 52 | Timeline list component |
| `components/features/pm/GroupBySelector.tsx` | 33 | Select dropdown for groupBy (status/team/assignee/dependency) |
| `pages/IssuesPage.tsx` | 110 | Issues page: filters, list, detail panel |
| **Sous-total frontend** | **1493** | |

### Frontend (hitl-frontend/tests/) — Fichiers tests nouveaux

| Fichier | Lignes | Tests |
|---|---|---|
| `tests/components/features/pm/IssueRow.test.tsx` | 66 | 6 tests |
| `tests/components/features/pm/IssueDetail.test.tsx` | 67 | 4 tests |
| `tests/components/features/pm/IssueCreateModal.test.tsx` | 53 | 4 tests |
| `tests/components/features/pm/PriorityBadge.test.tsx` | 36 | 4 tests |
| `tests/components/features/pm/IssueStatusIcon.test.tsx` | 42 | 5 tests |
| `tests/components/features/pm/InboxRow.test.tsx` | 45 | 4 tests |
| `tests/components/features/pm/GroupBySelector.test.tsx` | 20 | 2 tests |
| `tests/stores/issueStore.test.ts` | 59 | 5 tests |
| **Sous-total tests frontend** | **388** | **34 tests** |

### Total Phase 3a

| Categorie | Fichiers | Lignes | Tests |
|---|---|---|---|
| Backend source | 12 | 1283 | - |
| Backend tests | 7 | 954 | 47 |
| Frontend source | 22 | 1493 | - |
| Frontend tests | 8 | 388 | 34 |
| **Total** | **49** | **4118** | **81** |

---

## 2. Ecarts spec

| Ecart | Raison |
|---|---|
| `issue_helpers.py` split from `issue_service.py` | Le service depasse 300 lignes sans helpers. Le split isole row_to_response, log_activity, notify_on_update, check_unblock_cascade |
| Routes: `/issues/search` avant `/issues/{issue_id}` | FastAPI route ordering: les routes statiques doivent preceder les parametriques sinon "search" est capture comme issue_id |
| `_get_team_prefix` pour ID generation | Prefixe derive du team_id (4 chars max), pas de table de mapping separee |

---

## 3. Ecarts phases precedentes

| Fichier modifie | Modification |
|---|---|
| `core/pg_notify.py` | Nouveau channel `pm_updates` pour broadcast des changements PM en temps reel |
| `core/websocket_manager.py` | Ajout `broadcast_to_user(email, event)` pour notifications ciblees |
| `routes/ws.py` | Nouveau handler pour les events PM sur la connexion WebSocket existante |
| `main.py` | Import et include des 4 nouveaux routers (issues, relations, inbox, activity) |

---

## 4. Schemas API

### Issues

| Methode | Endpoint | Body/Query | Response | Status |
|---|---|---|---|---|
| `POST` | `/api/pm/issues?team_id=X` | `IssueCreate` (title, description, priority, status, assignee, tags, project_id, phase) | `IssueResponse` | 201 |
| `GET` | `/api/pm/issues?team_id&project_id&status&assignee&limit&offset` | - | `IssueResponse[]` | 200 |
| `GET` | `/api/pm/issues/search?q=X&team_id=X&limit` | - | `IssueResponse[]` | 200 |
| `GET` | `/api/pm/issues/{issue_id}` | - | `IssueDetail` (extends IssueResponse + relations + project_name) | 200/404 |
| `PUT` | `/api/pm/issues/{issue_id}` | `IssueUpdate` (all fields optional) | `IssueResponse` | 200/404 |
| `DELETE` | `/api/pm/issues/{issue_id}` | - | - | 204/404 |
| `POST` | `/api/pm/issues/bulk?team_id=X` | `IssueBulkCreate` (issues[], project_id) | `IssueResponse[]` | 201 |

### Relations

| Methode | Endpoint | Body | Response | Status |
|---|---|---|---|---|
| `POST` | `/api/pm/issues/{id}/relations` | `RelationCreate` (type, target_issue_id, reason) | `RelationResponse` | 201/400 |
| `GET` | `/api/pm/issues/{id}/relations` | - | `RelationResponse[]` | 200 |
| `DELETE` | `/api/pm/relations/{relation_id}` | - | - | 204/404 |
| `POST` | `/api/pm/issues/{id}/relations/bulk` | `RelationBulkCreate` (relations[]) | `RelationResponse[]` | 201 |

### Inbox

| Methode | Endpoint | Body | Response | Status |
|---|---|---|---|---|
| `GET` | `/api/pm/inbox?limit` | - | `NotificationResponse[]` | 200 |
| `PUT` | `/api/pm/inbox/{notif_id}/read` | - | `{ok: true}` | 200/404 |
| `PUT` | `/api/pm/inbox/read-all` | - | `{ok: true, count: N}` | 200 |
| `GET` | `/api/pm/inbox/count` | - | `{count: N}` | 200 |

### Activity

| Methode | Endpoint | Query | Response | Status |
|---|---|---|---|---|
| `GET` | `/api/pm/projects/{project_id}/activity?team_id&limit&offset` | - | `MergedActivityResponse` (entries[]) | 200 |

---

## 5. Composants React

| Composant | Props | Description |
|---|---|---|
| `IssueRow` | issue: IssueResponse, onClick, className? | Ligne issue avec ID mono, priority badge, status icon, blocked lock, tags, avatar |
| `IssueList` | issues: IssueResponse[], groupBy, onSelect, selectedId? | Liste groupee par status/team/assignee/dependency |
| `IssueDetail` | issue: IssueDetail, onUpdate, onDelete, onAddRelation?, className? | Detail panel avec champs editables, description, relations, delete |
| `IssueCreateModal` | open, onClose, onCreated, teamId, className? | Formulaire de creation (Modal) |
| `IssueStatusIcon` | status: IssueStatus, size?, className? | SVG icon pour 5 statuts |
| `PriorityBadge` | priority: IssuePriority, className? | 4 barres colorees (P1-P4) |
| `BlockedBanner` | blockedBy: {id, title}[] | Bandeau rouge blocage |
| `RelationList` | relations: RelationResponse[], onDelete | Liste avec direction et display_type |
| `AddRelationModal` | open, onClose, onCreated, issueId, teamId | Modal ajout relation avec recherche |
| `InboxBadge` | count: number | Badge rouge unread count |
| `InboxList` | notifications, onMarkRead, onMarkAllRead | Liste de notifications |
| `InboxRow` | notification: PMNotification, onMarkRead, className? | Ligne notification avec dot, texte, lien issue |
| `ActivityEntryRow` | entry: ActivityEntry | Ligne activite (PM ou agent) |
| `ActivityTimeline` | entries: ActivityEntry[] | Timeline verticale |
| `GroupBySelector` | value: IssueGroupBy, onChange, className? | Select avec 4 options |
| `IssuesPage` | - | Page complete: filtres, liste, detail panel |

---

## 6. Cles i18n

Cles ajoutees dans `public/locales/{fr,en}/translation.json` :

```
issue.create_title, issue.title, issue.description, issue.description_placeholder,
issue.priority, issue.priority_label, issue.status, issue.assignee, issue.team,
issue.phase, issue.tags, issue.tags_placeholder, issue.created_at, issue.no_description,
issue.add_relation, issue.blocking_count, issue.blocked_by,
issue.status_backlog, issue.status_todo, issue.status_in-progress,
issue.status_in-review, issue.status_done,
issue.group_status, issue.group_team, issue.group_assignee, issue.group_dependency,
inbox.title, inbox.mark_all_read, inbox.empty,
activity.title, activity.source_pm, activity.source_agent,
relation.blocks, relation.blocked_by, relation.relates_to, relation.parent,
relation.sub_task, relation.duplicates, relation.duplicated_by,
relation.add_title, relation.type, relation.target, relation.reason,
time.just_now, time.minutes_ago, time.hours_ago, time.days_ago
```

---

## 7. Tests

| Suite | Fichiers | Tests | Framework |
|---|---|---|---|
| Backend services | 4 | 29 | pytest + pytest-asyncio |
| Backend routes | 3 | 18 | pytest + httpx AsyncClient |
| Frontend components | 7 | 29 | vitest + @testing-library/react |
| Frontend stores | 1 | 5 | vitest + zustand |
| **Total** | **15** | **81** | |

---

## 8. Modifications fichiers existants

| Fichier | Modification |
|---|---|
| `hitl-new/main.py` (+8 lignes) | Import + include 4 routers (issues, relations, inbox, activity) |
| `hitl-new/core/pg_notify.py` (+12 lignes) | Channel `pm_updates` pour broadcast PM |
| `hitl-new/core/websocket_manager.py` (+15 lignes) | `broadcast_to_user()` pour notifications ciblees |
| `hitl-new/routes/ws.py` (+8 lignes) | Handler events PM sur WebSocket |
| `hitl-frontend/src/router.tsx` (+3 lignes) | Route `/issues` vers IssuesPage |
| `hitl-frontend/src/components/layout/Sidebar.tsx` (+8 lignes) | Lien Issues + InboxBadge |
| `hitl-frontend/src/pages/InboxPage.tsx` (+15 lignes) | Integration InboxList PM |
| `hitl-frontend/src/pages/DashboardPage.tsx` (+10 lignes) | Widget issues recentes |
| `hitl-frontend/src/api/types.ts` (+102 lignes) | Types PM (IssueResponse, IssueDetail, RelationResponse, PMNotification, etc.) |
| `hitl-frontend/public/locales/fr/translation.json` | +50 cles i18n PM |
| `hitl-frontend/public/locales/en/translation.json` | +50 cles i18n PM |

---

## 9. Points Phase 3b

| Sujet | Description |
|---|---|
| Pull Requests | Liens auto-generes vers GitHub PRs dans l'activite |
| Merge / QA | Integration du statut CI/CD dans les issues |
| Pulse | Dashboard pulse : metriques hebdo (issues created/closed, velocity) |
| Workflow visuel | Vue kanban du workflow avec drag-drop entre colonnes |
| Agent dispatch | Dispatch automatique d'agents sur les issues via workflow engine |

---

## 10. Commandes

### Dev

```bash
# Backend
cd hitl-new && pip install -r requirements.txt && uvicorn main:app --reload --port 8090

# Frontend
cd hitl-frontend && npm install && npm run dev
```

### Tests

```bash
# Backend (depuis hitl-new/)
pytest tests/test_issue_service.py tests/test_relation_service.py tests/test_inbox_service.py tests/test_activity_service.py tests/test_issue_routes.py tests/test_relation_routes.py tests/test_inbox_routes.py -v

# Frontend (depuis hitl-frontend/)
npx vitest run tests/components/features/pm/ tests/stores/issueStore.test.ts
```

### Build

```bash
# Frontend production build
cd hitl-frontend && npm run build

# Docker
docker compose build hitl-console
```
