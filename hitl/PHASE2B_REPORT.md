# Phase 2b — Livrables + Chat + Dashboard — Rapport de fin de phase

> **Date** : 2026-03-22
> **Scope** : hitl-new/ (backend), hitl-frontend/ (frontend), scripts/init.sql

---

## 1. Inventaire des fichiers

### Backend — Nouveaux fichiers (10)

| Fichier | Lignes | Role |
|---|---|---|
| `schemas/deliverable.py` | 80 | DeliverableResponse, DeliverableDetail, ValidateRequest, RemarkRequest/Response, BranchInfo, BranchDiffResponse |
| `schemas/chat.py` | 35 | ChatMessageResponse, SendMessageRequest, AgentResponse |
| `services/deliverable_service.py` | 246 | CRUD livrables, validate, content read/write |
| `services/validation_service.py` | 100 | Copie vers repo + git commit + append _validations.json |
| `services/chat_service.py` | 141 | Chat history, send message (gateway invoke), clear |
| `services/dashboard_service.py` | 89 | Proxy dispatcher (active tasks, costs, overview) |
| `routes/deliverables.py` | 173 | 8 endpoints livrables + branches |
| `routes/chat.py` | 51 | 3 endpoints chat agents |
| `routes/agents.py` | 84 | 1 endpoint liste agents avec pending counts |
| `routes/dashboard.py` | 42 | 3 endpoints dashboard |

### Backend — Fichiers modifies (5)

| Fichier | Modification |
|---|---|
| `main.py` | +4 imports + 4 include_router |
| `core/pg_notify.py` | +hitl_chat channel dispatch via broadcast_watched |
| `core/websocket_manager.py` | +_watched dict, watch_chat, unwatch_chat, broadcast_watched |
| `routes/ws.py` | +handle watch_chat/unwatch_chat messages |
| `scripts/init.sql` | +deliverable_remarks table + budget column |

### Backend — Tests (6)

| Fichier | Lignes | Tests |
|---|---|---|
| `test_deliverable_service.py` | 167 | 8 |
| `test_chat_service.py` | 78 | 4 |
| `test_dashboard_service.py` | 98 | 5 |
| `test_deliverable_routes.py` | 151 | 7 |
| `test_chat_routes.py` | 68 | 3 |
| `test_agents_routes.py` | 46 | 2 |
| **Total** | **608** | **29** |

### Frontend — Nouveaux fichiers (30)

| Categorie | Fichiers | Lignes |
|---|---|---|
| API (deliverables, chat, agents, dashboard) | 4 | 118 |
| Stores (deliverableStore, chatStore) | 2 | 79 |
| Composants livrables (9) | 9 | 558 |
| Composants chat (4) + agent (2) | 6 | 320 |
| Composants dashboard (5) | 5 | 332 |
| Pages (4) | 4 | 233 |
| **Total** | **30** | **1640** |

### Frontend — Fichiers modifies (6)

| Fichier | Modification |
|---|---|
| `api/types.ts` | +11 interfaces |
| `router.tsx` | +5 routes |
| `components/layout/Sidebar.tsx` | +Dashboard item + Agents item |
| `public/locales/fr/translation.json` | +6 groupes cles |
| `public/locales/en/translation.json` | Idem anglais |
| `package.json` | +react-markdown, remark-gfm, react-syntax-highlighter |

### Frontend — Tests (8)

| Fichier | Lignes | Tests |
|---|---|---|
| `DeliverableCard.test.tsx` | 56 | 5 |
| `DeliverableActions.test.tsx` | 43 | 5 |
| `MarkdownRenderer.test.tsx` | 29 | 4 |
| `ChatBubble.test.tsx` | 39 | 3 |
| `AgentCard.test.tsx` | 36 | 3 |
| `ActiveTasksList.test.tsx` | 35 | 3 |
| `CostSummaryCard.test.tsx` | 45 | 3 |
| `deliverableStore.test.ts` | 69 | 4 |
| **Total** | **352** | **30** |

### Totaux Phase 2b

| Categorie | Fichiers | Lignes |
|---|---|---|
| Backend code | 10 | 1041 |
| Backend tests | 6 | 608 |
| Frontend code | 30 | 1640 |
| Frontend tests | 8 | 352 |
| SQL | 1 | +15 |
| **Grand total** | **55 fichiers** | **~3660 lignes** |

---

## 2. Ecarts avec la spec

| Point | Implementation | Raison |
|---|---|---|
| deliverable_service.py en 1 fichier | **Decoupe** en deliverable_service.py (246) + validation_service.py (100) | Respect limite 300 lignes |
| CostByAgentChart | **CSS bars** (pas de lib chart) | Comme prevu dans le spec — barres horizontales en CSS pur |
| Default route | Change de `/inbox` a `/dashboard` | Le dashboard est la vue d'ensemble logique comme page d'accueil |
| Agents page route | `/teams/:teamId/agents` | Comme prevu |

---

## 3. Ecarts avec les Phases 0, 1, 2a

| Point | Phase precedente | Phase 2b | Alignement |
|---|---|---|---|
| pg_notify.py | 4 channels (hitl_request, hitl_response, task_progress, task_artifact) | +hitl_chat | Ajout non destructif |
| websocket_manager.py | broadcast(team_id, event_type, data) | +broadcast_watched + watch_chat/unwatch_chat | Retrocompat |
| routes/ws.py | Recoit pong seulement | +watch_chat/unwatch_chat | Ajout non destructif |
| dispatcher_task_artifacts | Lecture seule | **Ecriture** : UPDATE status, reviewer, review_comment, reviewed_at | Comme prevu dans le spec Phase 0 |
| git_service._run_git | Utilise par init/clone/status | +commit sur branche dev (validation livrables) | Reutilisation existante |

---

## 4. Schemas et contrats d'API reels

### GET /api/projects/{slug}/deliverables
```
Query:    ?phase=&agent_id=&status=
Response: DeliverableResponse[] { id, task_id, key, deliverable_type, file_path, git_branch, category,
          status, reviewer, review_comment, reviewed_at, created_at, agent_id, phase, project_slug }
```

### GET /api/deliverables/{id}
```
Response: DeliverableDetail { ...DeliverableResponse + content (str), cost_usd (float) }
Errors:   404 { key: "deliverable.not_found" }
```

### PUT /api/deliverables/{id}/content
```
Request:  { content: str }
Response: { ok: true }
```

### POST /api/deliverables/{id}/validate
```
Request:  { verdict: "approved"|"rejected", comment?: str }
Response: { ok: true, copied_to?: str }
Errors:   409 { key: "deliverable.already_validated" }
```

### POST /api/deliverables/{id}/remark
```
Request:  { comment: str }
Response: RemarkResponse { id, artifact_id, reviewer, comment, created_at }
```

### GET /api/deliverables/{id}/remarks
```
Response: RemarkResponse[]
```

### GET /api/projects/{slug}/branches
```
Response: BranchInfo[] { name, ahead, behind, last_commit }
```

### GET /api/projects/{slug}/branches/{branch}/diff
```
Response: BranchDiffResponse { branch, files: [{path, status, additions, deletions}] }
```

### GET /api/teams/{id}/agents/{id}/chat
```
Response: ChatMessageResponse[] { id, team_id, agent_id, thread_id, sender, content, created_at }
```

### POST /api/teams/{id}/agents/{id}/chat
```
Request:  { message: str }
Response: ChatMessageResponse (agent's response)
```

### DELETE /api/teams/{id}/agents/{id}/chat
```
Response: { ok: true, deleted: int }
```

### GET /api/teams/{id}/agents
```
Response: AgentResponse[] { id, name, llm, type, pending_questions }
```

### GET /api/dashboard/active-tasks
```
Query:    ?team_id=
Response: list (proxy dispatcher, [] if down)
```

### GET /api/dashboard/costs/{slug}
```
Response: dict (proxy dispatcher, null if down)
```

### GET /api/dashboard/overview
```
Response: { pending_questions, active_tasks, total_cost }
```

---

## 5. Composants React reels

### Livrables

| Composant | Props |
|---|---|
| `DeliverableList` | deliverables, loading, onSelect(id), className? |
| `DeliverableCard` | deliverable (DeliverableResponse), onClick, className? |
| `DeliverableDetail` | deliverable (DeliverableDetail), onValidate, onRemark, className? |
| `DeliverableActions` | status, onApprove, onReject, onRemark, onEdit, className? |
| `MarkdownRenderer` | content (string), className? |
| `RemarkForm` | onSubmit(comment), loading?, className? |
| `ValidationBadge` | status, reviewer?, className? |
| `BranchList` | branches (BranchInfo[]), onSelect(name), className? |
| `BranchDiff` | branch, files (BranchDiffFile[]), className? |

### Chat + Agents

| Composant | Props |
|---|---|
| `AgentGrid` | agents (AgentInfo[]), teamId, className? |
| `AgentCard` | agent (AgentInfo), teamId, className? |
| `AgentChat` | teamId, agentId, className? |
| `ChatBubble` | message (ChatMessage), isUser (bool), className? |
| `ChatInput` | onSend(message), loading?, placeholder?, className? |
| `ChatTypingIndicator` | agentName, className? |

### Dashboard

| Composant | Props |
|---|---|
| `OverviewCards` | data (OverviewData), className? |
| `ActiveTasksList` | tasks (ActiveTask[]), className? |
| `TaskProgressCard` | task (ActiveTask), className? |
| `CostSummaryCard` | costs (CostSummary[]), budget (number), className? |
| `CostByAgentChart` | costs (CostSummary[]), className? |

---

## 6. Nouvelles cles i18n

### Frontend

```
deliverable: deliverables, no_deliverables, no_deliverables_desc, phase, agent, type, category,
  status, content, pending, approved, rejected, approve, reject, approve_confirm, reject_confirm,
  remark, remark_placeholder, remark_submit, remarks, no_remarks, edit, save_edit,
  validated_by, rejected_by, copied_to
chat: history, send, placeholder, clear, clear_confirm, typing, no_messages, no_messages_desc
agent: agents, online, offline, pending_questions, llm, type
dashboard: title, active_tasks, no_active_tasks, costs, total_cost, cost_by_phase, cost_by_agent,
  projection, projected_total, budget_warning, overview, pending_questions, active_agents,
  dispatcher_offline
branch: branches, diff, files_changed, ahead, behind, no_branches
nav: dashboard (added)
```

### Backend (ajout dans i18n/fr.json et en.json)

```
deliverable.not_found, deliverable.already_validated
chat.send_failed, chat.gateway_unavailable
dashboard.dispatcher_offline
```

---

## 7. Etat des tests

| Categorie | Tests | Etat |
|---|---|---|
| Backend test_deliverable_service | 8 | Non execute |
| Backend test_chat_service | 4 | Non execute |
| Backend test_dashboard_service | 5 | Non execute |
| Backend test_deliverable_routes | 7 | Non execute |
| Backend test_chat_routes | 3 | Non execute |
| Backend test_agents_routes | 2 | Non execute |
| Frontend DeliverableCard | 5 | Non execute |
| Frontend DeliverableActions | 5 | Non execute |
| Frontend MarkdownRenderer | 4 | Non execute |
| Frontend ChatBubble | 3 | Non execute |
| Frontend AgentCard | 3 | Non execute |
| Frontend ActiveTasksList | 3 | Non execute |
| Frontend CostSummaryCard | 3 | Non execute |
| Frontend deliverableStore | 4 | Non execute |
| **Total Phase 2b** | **59** | Tests unitaires mocks |

**Total cumule Phases 1+2a+2b** : 237 tests (107+71+59)

---

## 8. Modifications fichiers existants

| Fichier | Detail |
|---|---|
| `hitl-new/main.py` | 4 nouveaux routers montes |
| `hitl-new/core/pg_notify.py` | Channel `hitl_chat` ajoute + dispatch via `broadcast_watched` |
| `hitl-new/core/websocket_manager.py` | Dict `_watched`, methodes `watch_chat`, `unwatch_chat`, `broadcast_watched` |
| `hitl-new/routes/ws.py` | Handler `_handle_ws_message` pour watch_chat/unwatch_chat |
| `hitl-frontend/src/router.tsx` | 5 routes ajoutees + redirect defaut vers /dashboard |
| `hitl-frontend/src/components/layout/Sidebar.tsx` | Items Dashboard (global) + Agents (par equipe) |
| `hitl-frontend/src/api/types.ts` | 11 interfaces TypeScript ajoutees |
| `hitl-frontend/package.json` | 3 deps (react-markdown, remark-gfm, react-syntax-highlighter) |
| `hitl-frontend/public/locales/fr/translation.json` | 6 groupes de cles |
| `hitl-frontend/public/locales/en/translation.json` | Idem anglais |
| `scripts/init.sql` | Table deliverable_remarks + colonne budget |

---

## 9. Points d'attention pour la Phase 3

### Production Manager (issues, PRs, pulse)

1. **pm_issues** : table existante, endpoints a creer dans la console (CRUD issues, assignation, statuts)
2. **pm_pull_requests** : table existante, integration git (creer PR via API GitHub/GitLab)
3. **pm_inbox** : notifications utilisateur (mentions, assignments, status changes)
4. **pm_activity** : log d'activite par projet
5. **pulse** : metriques agregees (velocity, burndown, etc.)

### Workflow visuel

1. Le workflow editor existe dans l'admin dashboard (web/static/js/app.js) — peut etre reimplemente en React
2. Les categories de livrables (Phase 0 categories feature) doivent etre affichees dans la vue livrables
3. Le Workflow.json definit les phases, agents, livrables — la console doit le lire pour afficher le progress

### Merge et QA

1. Les branches `temp/*` sont visibles mais pas fusionnables depuis la console
2. Phase 3 ajoutera : creer PR, review, merge vers dev, QA automatique
3. Le QA engineer est un agent qui peut etre lance via le dispatcher

### Architecture preparee

- `deliverableStore` expose `deliverables` et `selectedId` reutilisables
- `chatStore` gere l'historique agent par agent
- `dashboard_service` a le proxy dispatcher avec fallback gracieux
- `MarkdownRenderer` est reutilisable partout (issues, PRs, etc.)
- WebSocket watch_chat pattern extensible pour d'autres subscriptions

---

## 10. Commandes de lancement

### Backend
```bash
cd hitl-new && pip install -r requirements.txt
DATABASE_URI=postgresql://user:pass@localhost:5432/langgraph \
  python -m uvicorn main:app --port 8090 --reload
```

### Frontend
```bash
cd hitl-frontend && npm install && npm run dev
```

### Tests
```bash
cd hitl-new && pytest tests/ -v --tb=short
cd hitl-frontend && npm run test
```

### Appliquer le schema SQL
```bash
docker exec -i langgraph-postgres psql -U langgraph -d langgraph < scripts/init.sql
```
