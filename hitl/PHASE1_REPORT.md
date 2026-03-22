# Phase 1 — Console HITL : Socle — Rapport de fin de phase

> **Date** : 2026-03-22
> **Service** : `langgraph-hitl` (port 8090)
> **Stack backend** : Python 3.11, FastAPI, asyncpg, python-jose, passlib, structlog
> **Stack frontend** : React 18, Vite 5, TypeScript strict, Tailwind CSS 3, Zustand 4, react-i18next 13

---

## 1. Inventaire des fichiers

### Backend (`hitl-new/`)

| Fichier | Lignes | Role |
|---|---|---|
| `main.py` | 192 | App FastAPI, lifespan, seed admin, CORS, static mount |
| `core/config.py` | 95 | pydantic-settings, lecture hitl.json/mail.json/others.json |
| `core/database.py` | 73 | Pool asyncpg (init/close/get/execute/fetch) |
| `core/security.py` | 103 | JWT HS256, bcrypt, get_current_user dependency |
| `core/websocket_manager.py` | 54 | Connexions WS par team_id, broadcast |
| `core/pg_notify.py` | 85 | PG LISTEN hitl_request + hitl_response, dispatch WS |
| `models/user.py` | 34 | Dataclasses User, TeamMember |
| `models/hitl.py` | 42 | Dataclasses HitlRequest, ChatMessage |
| `schemas/auth.py` | 59 | LoginRequest, RegisterRequest, GoogleAuthRequest, TokenResponse, UserResponse |
| `schemas/common.py` | 28 | ErrorResponse, SuccessResponse, PaginationParams |
| `schemas/team.py` | 38 | TeamResponse, TeamMemberResponse, InviteRequest |
| `schemas/hitl.py` | 44 | QuestionResponse, AnswerRequest, StatsResponse |
| `services/auth_service.py` | 242 | Login, register, Google OAuth, reset password, get_me |
| `services/email_service.py` | 139 | SMTP config from mail.json, send reset email |
| `services/team_service.py` | 127 | List teams (config enriched), members, invite |
| `services/hitl_service.py` | 158 | List/filter questions, answer, stats |
| `routes/auth.py` | 61 | 6 endpoints auth |
| `routes/health.py` | 43 | /health + /api/version |
| `routes/teams.py` | 52 | 3 endpoints equipes |
| `routes/hitl.py` | 76 | 4 endpoints questions |
| `routes/ws.py` | 63 | WebSocket /api/teams/{id}/ws |
| `i18n/fr.json` | 21 | Cles d'erreur backend (francais) |
| `i18n/en.json` | 21 | Cles d'erreur backend (anglais) |
| `requirements.txt` | 12 | Dependances Python |
| `tests/conftest.py` | 112 | Fixtures partagees |
| `tests/test_auth.py` | 182 | 12 tests auth |
| `tests/test_teams.py` | 111 | 6 tests equipes |
| `tests/test_hitl.py` | 125 | 6 tests HITL |
| `tests/test_websocket.py` | 115 | 4 tests WebSocket |
| `tests/test_security.py` | 111 | 10 tests securite |
| **Total backend** | **2618** | **27 fichiers Python/JSON** |

### Frontend (`hitl-frontend/`)

| Categorie | Fichiers | Lignes |
|---|---|---|
| Config (package.json, vite, ts, tailwind, postcss) | 6 | 175 |
| Core (main, App, router, i18n, globals.css) | 5 | 112 |
| API (client, auth, teams, hitl, types) | 5 | 285 |
| Stores (auth, team, ws, notification) | 4 | 178 |
| Hooks (useAuth, useWebSocket, useNotifications) | 3 | 183 |
| Composants UI (11 composants) | 11 | 592 |
| Composants Layout (8 composants) | 8 | 452 |
| Composants Features (9 composants) | 9 | 825 |
| Pages (6 pages) | 6 | 352 |
| i18n (fr + en + sw.js) | 3 | 173 |
| Tests (11 fichiers) | 12 | 834 |
| **Total frontend** | **72 fichiers** | **4161 lignes** |

### Infrastructure

| Fichier | Lignes | Role |
|---|---|---|
| `Dockerfile.hitl-new` | 17 | Multi-stage: node:20 build frontend + python:3.11 runtime |

### Grand total

- **Backend** : 27 fichiers, 2618 lignes
- **Frontend** : 72 fichiers, 4161 lignes
- **Total** : 99 fichiers, ~6800 lignes
- **Contrainte < 300 lignes** : respectee (max = 242 : auth_service.py)

---

## 2. Ecarts avec la spec

| Point de la spec | Implementation | Raison |
|---|---|---|
| SQLAlchemy async | **asyncpg brut** | Coherence avec le dispatcher (meme pattern DB dans tout le projet) |
| `hitl/` comme repertoire | **`hitl-new/`** | L'ancien `hitl/` existe encore — evite conflit pendant la transition |
| Dockerfile.hitl | **Dockerfile.hitl-new** | Idem, l'ancien Dockerfile.hitl existe |
| Ajout `types.ts` dans l'API | **Ajoute** | Necessaire pour le typage strict TypeScript (interfaces partagees) |
| Ajout `AuthGuard.tsx` | **Ajoute** | Composant wrapper pour les routes protegees (prevu dans router mais pas liste comme fichier) |
| `vitest.config.ts` separe | **Ajoute** | Meilleure separation de la config Vitest vs Vite |
| Service Worker | **Stub minimal** | Comme prevu : install + activate, pas de push notifications |
| docker-compose.yml non modifie | **Non modifie** | Sera fait au moment du deploiement quand on bascule de hitl/ vers hitl-new/ |

---

## 3. Ecarts avec la Phase 0 (Dispatcher)

| Point | Phase 0 (dispatcher) | Phase 1 (console) | Alignement |
|---|---|---|---|
| Tables | `dispatcher_tasks`, `_events`, `_artifacts`, `_cost_summary` | Lecture seule sur ces tables | OK, pas de conflit |
| PG NOTIFY channels | `hitl_request`, `hitl_response`, `task_progress`, `task_artifact` | Ecoute `hitl_request` + `hitl_response` | OK, Phase 2 ajoutera `task_progress` + `task_artifact` |
| hitl_requests.channel | `'docker'` pour les requetes du dispatcher | Filtre par channel dans l'inbox | OK |
| depends_on dispatcher | Non requis | La console fonctionne sans le dispatcher (fallback gracieux) | OK |
| Trigger SQL `notify_hitl_response` | Cree en Phase 0 dans init.sql | Utilise tel quel | OK, pas de conflit |

---

## 4. Schemas et contrats d'API reels

### POST /api/auth/login
```
Request:  { email: string, password: string }
Response: { token: string, user: { id, email, display_name, role, auth_type, culture, teams } }
Errors:   401 { key: "auth.invalid_credentials" }
          403 { key: "auth.account_pending" }
          403 { key: "auth.account_disabled" }
```

### POST /api/auth/register
```
Request:  { email: string, culture: string = "fr" }
Response: { ok: true }
Errors:   409 { key: "auth.email_exists" }
```

### POST /api/auth/google
```
Request:  { credential: string }  (Google ID token)
Response: { token: string, user: UserResponse }
Errors:   400 { key: "auth.google_not_configured" }
          401 { key: "auth.google_invalid_token" }
          401 { key: "auth.google_domain_not_allowed" }
          403 { key: "auth.account_pending" }
```

### GET /api/auth/google/client-id
```
Response: { client_id: string | null, enabled: bool }
```

### GET /api/auth/me (JWT)
```
Response: UserResponse { id, email, display_name, role, auth_type, culture, teams }
Errors:   401 (invalid/missing JWT)
```

### POST /api/auth/reset-password
```
Request:  { email: string, old_password: string, new_password: string }
Response: { ok: true }
Errors:   401 { key: "auth.password_mismatch" }
          400 { key: "auth.weak_password" }
```

### GET /api/teams (JWT)
```
Response: TeamResponse[] { id, name, directory, member_count }
```

### GET /api/teams/{id}/members (JWT)
```
Response: TeamMemberResponse[] { user_id, email, display_name, role_global, role_team, is_active, last_login }
Errors:   403 { key: "team.access_denied" }
```

### POST /api/teams/{id}/members (JWT, admin only)
```
Request:  { email: string, display_name: string = "", role: string = "member" }
Response: { ok: true }
Errors:   403 { key: "common.forbidden" }
          409 { key: "team.member_exists" }
```

### GET /api/teams/{id}/questions (JWT)
```
Query:    ?status=pending&channel=docker&offset=0&limit=50
Response: QuestionResponse[] { id, thread_id, agent_id, team_id, request_type, prompt, context, channel, status, response, reviewer, created_at, answered_at }
```

### GET /api/teams/{id}/questions/stats (JWT)
```
Response: StatsResponse { pending, answered, timeout, cancelled, total }
```

### GET /api/questions/{id} (JWT)
```
Response: QuestionResponse
Errors:   404 { key: "hitl.question_not_found" }
```

### POST /api/questions/{id}/answer (JWT)
```
Request:  { response: string, action: "answer" | "approve" | "reject" }
Response: { ok: true }
Errors:   404 { key: "hitl.question_not_found" }
          409 { key: "hitl.already_answered" }
```

### WebSocket /api/teams/{id}/ws?token={jwt}
```
Server → Client:  { type: "ping" | "new_question" | "question_answered", data: {...} }
Client → Server:  { type: "pong" }
Close codes:      4001 (Unauthorized), 4003 (Forbidden)
```

### GET /health
```
Response: { status: "ok" | "degraded", db: bool }
```

### GET /api/version
```
Response: { version: string, service: "hitl-console" }
```

---

## 5. Composants React reels

### Composants UI

| Composant | Props |
|---|---|
| `Button` | variant (primary\|secondary\|danger\|ghost), size (sm\|md\|lg), loading?, disabled?, icon?, children, onClick?, type?, className? |
| `Input` | label?, error?, icon?, className? + native InputHTMLAttributes |
| `Select` | label?, error?, options ({value, label}[]), className? + native SelectHTMLAttributes |
| `Card` | variant (flat\|elevated\|interactive), children, className?, onClick? |
| `Badge` | variant (status\|count\|tag), color (blue\|green\|orange\|red\|purple\|yellow), size? (sm\|md), children, className? |
| `Avatar` | name (string), size? (sm\|md\|lg), className? |
| `StatusDot` | status (online\|offline\|pending\|busy), size? (sm\|md), className? |
| `Modal` | open, onClose, titleKey (i18n), children, actions?, className? |
| `Toast` | (via notificationStore) type (success\|error\|info\|warning), messageKey, params? |
| `Spinner` | size? (sm\|md\|lg), className? |
| `EmptyState` | icon?, titleKey, descriptionKey?, action?, className? |

### Composants Layout

| Composant | Props |
|---|---|
| `Sidebar` | (no props — reads from stores) |
| `SidebarItem` | icon, labelKey, to, badge?, active?, collapsed? |
| `SidebarTeamGroup` | team ({id, name}), expanded, onToggle, children |
| `Header` | titleKey, actions?, children? |
| `MobileNav` | (no props — reads from stores) |
| `PageContainer` | children, className? |
| `DetailPanel` | open, onClose, title, children, actions? |
| `AuthGuard` | children |

### Composants Features

| Composant | Props |
|---|---|
| `LoginForm` | (no props — uses hooks) |
| `RegisterForm` | (no props) |
| `GoogleSignIn` | onSuccess(credential) |
| `ResetPasswordForm` | (reads URL params) |
| `QuestionCard` | question (QuestionResponse), onAnswer?, onApprove?, onReject? |
| `QuestionList` | questions, loading?, emptyStateKey? |
| `AnswerModal` | question, open, onClose, onSubmit |
| `MemberList` | members, onInvite?, onRemove?, isAdmin? |
| `InviteMemberModal` | open, onClose, onInvite, teamId |

---

## 6. Cles i18n reelles

### Frontend (public/locales/{lang}/translation.json)

```
common: save, cancel, delete, confirm, loading, error, success, search, no_results, back, logout, close
auth: login, register, email, password, new_password, confirm_password, forgot_password, sign_in_google,
      invalid_credentials, account_pending, account_disabled, register_success, reset_success,
      culture, password_min_length, passwords_dont_match, login_title, register_title, reset_title
nav: inbox, teams, members, agents, activity, settings
hitl: questions, pending, answered, timeout, cancelled, approve, reject, answer, answer_placeholder,
      new_question_title, new_question_body, no_pending, stats, all_channels, filter_status,
      filter_team, filter_channel, all_statuses, all_teams, question, approval
team: members, invite, invite_email, invite_role, remove, role_admin, role_member, invite_success
notifications: permission_denied, new_question
time: just_now, minutes_ago, hours_ago, days_ago
errors: not_found_title, not_found_description, go_home
app: title, version
```

### Backend (i18n/{lang}.json) — cles d'erreur

```
auth.invalid_credentials, auth.account_pending, auth.account_disabled, auth.email_exists,
auth.google_not_configured, auth.google_invalid_token, auth.google_domain_not_allowed,
auth.password_mismatch, auth.weak_password,
team.not_found, team.access_denied, team.member_exists,
hitl.question_not_found, hitl.already_answered,
common.not_found, common.forbidden, common.server_error
```

---

## 7. Etat des tests

### Backend

| Fichier | Tests | Etat |
|---|---|---|
| test_security.py | 10 | Non execute (pas de DB locale) |
| test_auth.py | 12 | Non execute |
| test_teams.py | 6 | Non execute |
| test_hitl.py | 6 | Non execute |
| test_websocket.py | 4 | Non execute |
| **Total** | **38** | Ecrits, mocks unitaires |

### Frontend

| Fichier | Tests | Etat |
|---|---|---|
| Button.test.tsx | 9 | Non execute (npm install requis) |
| Modal.test.tsx | 6 | Non execute |
| Badge.test.tsx | 9 | Non execute |
| Toast.test.tsx | 5 | Non execute |
| Sidebar.test.tsx | 7 | Non execute |
| LoginForm.test.tsx | 9 | Non execute |
| QuestionCard.test.tsx | 9 | Non execute |
| useWebSocket.test.ts | 5 | Non execute |
| authStore.test.ts | 6 | Non execute |
| InboxPage.test.tsx | 4 | Non execute |
| **Total** | **69** | Ecrits, mocks unitaires |

**Grand total : 107 tests** (38 backend + 69 frontend)

> Note : les tests utilisent des mocks et ne necessitent pas de services reels.

---

## 8. Points d'attention pour la Phase 2

### Architecture preparee

1. **WebSocket manager** supporte `broadcast(team_id, event_type, data)` — ajout facile de nouveaux event types (task_progress, task_artifact)
2. **PG NOTIFY listener** peut etre etendu avec de nouveaux channels sans modifier l'existant (`listener.listen(["task_progress", "task_artifact"])`)
3. **Router** a des commentaires marquant ou ajouter les routes Phase 2 (`/projects`, `/teams/:id/agents`, etc.)
4. **DetailPanel** accepte un slot `actions` pour les boutons de validation de livrables
5. **teamStore** expose `activeTeamId` utilisable par les pages Phase 2
6. **API client** est generique — ajouter de nouveaux modules (`api/projects.ts`, `api/dispatcher.ts`) est trivial
7. **i18n** structure est extensible — ajouter des namespaces ou des cles dans les JSON existants

### Integration dispatcher (Phase 2)

- `GET /api/tasks/active` : le backend doit appeler `http://langgraph-dispatcher:8070/api/tasks/active` via httpx dans un try/except → retourner `[]` si le dispatcher est down
- `dispatcher_task_artifacts` : la console doit UPDATE `status`, `reviewer`, `review_comment`, `reviewed_at` pour la validation des livrables
- Channels PG NOTIFY `task_progress` et `task_artifact` : ajouter au listener dans pg_notify.py

### Points techniques

- Le repertoire s'appelle `hitl-new/` et `hitl-frontend/` — a la bascule en production, renommer `hitl/` → `hitl-legacy/` et `hitl-new/` → `hitl/`
- Le Dockerfile est `Dockerfile.hitl-new` — renommer en `Dockerfile.hitl` a la bascule
- Le frontend build se met dans `dist/` (Vite) → copie dans `static/` du backend dans le Docker multi-stage

---

## 9. Commandes de lancement

### Backend (dev)
```bash
cd hitl-new
pip install -r requirements.txt
DATABASE_URI=postgresql://user:pass@localhost:5432/langgraph \
  python -m uvicorn main:app --host 0.0.0.0 --port 8090 --reload
```

### Frontend (dev)
```bash
cd hitl-frontend
npm install
npm run dev
# → http://localhost:3001 (proxy API vers :8090)
```

### Tests backend
```bash
cd hitl-new
pip install pytest pytest-asyncio
pytest tests/ -v --tb=short
```

### Tests frontend
```bash
cd hitl-frontend
npm run test
```

### Build Docker
```bash
docker build -f Dockerfile.hitl-new -t langgraph-hitl .
```

### Deploiement
```bash
# Quand pret a basculer :
# 1. Renommer hitl/ → hitl-legacy/
# 2. Renommer hitl-new/ → hitl/
# 3. Renommer Dockerfile.hitl-new → Dockerfile.hitl
# 4. bash deploy.sh AGT1
```
