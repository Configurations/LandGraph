# Audit des valeurs hardcodees — LandGraph

> **Date** : 2026-03-22
> **Scope** : hitl-new/, dispatcher/, hitl-frontend/src/
> **Fichiers scannes** : ~350 fichiers (.py, .ts, .tsx)

---

## 1. URLs de services en dur

| Fichier | Ligne | Valeur | Devrait etre | Criticite |
|---|---|---|---|---|
| `hitl-new/services/analysis_service.py` | 24 | `"http://langgraph-hitl:8090/api/internal/rag/search"` | `settings.hitl_internal_url` ou env var `RAG_ENDPOINT` | **HAUTE** |
| `hitl-new/services/rag_service.py` | ~78 | `"http://localhost:11434"` (fallback Ollama) | Env var `OLLAMA_BASE_URL` ou config llm_providers.json | **HAUTE** |
| `dispatcher/core/config.py` | 9 | `"postgresql://langgraph:langgraph@langgraph-postgres:5432/langgraph"` | Env var `DATABASE_URI` (deja lue mais default expose les creds) | **HAUTE** |
| `dispatcher/core/config.py` | 10 | `"redis://:langgraph@langgraph-redis:6379/0"` | Env var `REDIS_URI` (idem) | **HAUTE** |
| `dispatcher/core/config.py` | 16 | `"http://langgraph-api:8000"` | Env var `LANGGRAPH_API_URL` (deja lue mais default en dur) | Moyenne |
| `hitl-new/core/config.py` | 30 | `"http://localhost:8090"` | Env var `HITL_PUBLIC_URL` (deja lue) | Moyenne |
| `hitl-new/core/config.py` | 31 | `"http://langgraph-dispatcher:8070"` | Env var `DISPATCHER_URL` (deja lue) | Moyenne |

**Note** : les 4 derniers sont des defaults dans pydantic-settings — l'env var les surcharge. Le risque est que le default expose des infos si l'env var n'est pas definie.

---

## 2. Agent IDs en dur

| Fichier | Ligne | Valeur | Devrait etre | Criticite |
|---|---|---|---|---|
| `hitl-new/services/analysis_service.py` | 27 | `"project_analyst"` | Parametre de la fonction ou config workflow | **MOYENNE** |

Tous les autres agent IDs sont dans des fichiers de test (safe).

---

## 3. Thread ID patterns en dur

| Fichier | Ligne | Valeur | Devrait etre | Criticite |
|---|---|---|---|---|
| `hitl-new/services/analysis_service.py` | 29 | `f"analysis-{project_slug}"` | Constante `ANALYSIS_THREAD_PREFIX` | Basse |
| `hitl-new/services/chat_service.py` | ~25 | `f"hitl-chat-{team_id}-{agent_id}"` | Constante `CHAT_THREAD_PREFIX` | Basse |

---

## 4. Canaux PG NOTIFY en dur

| Fichier | Ligne(s) | Valeurs | Devrait etre | Criticite |
|---|---|---|---|---|
| `hitl-new/core/pg_notify.py` | 31-34, 69-94 | `"hitl_request"`, `"hitl_response"`, `"task_progress"`, `"task_artifact"`, `"hitl_chat"`, `"pm_inbox"` | Module `core/channels.py` avec constantes nommees | **MOYENNE** |
| `dispatcher/core/events.py` | ~69 | `"hitl_response"` | Constante partagee | **MOYENNE** |
| `dispatcher/services/task_runner.py` | ~158, 166 | `"task_progress"`, `"task_artifact"` | Constantes | **MOYENNE** |
| `dispatcher/services/hitl_bridge.py` | ~40 | `"hitl_request"` | Constante | **MOYENNE** |

**Risque** : si on renomme un canal d'un cote sans l'autre, la communication casse silencieusement.

---

## 5. Noms de tables/schema en dur

| Pattern | Nombre d'occurrences | Fichiers | Criticite |
|---|---|---|---|
| `project.dispatcher_tasks` | ~15 | task_db, task_runner, dashboard_service, workflow_service | Basse |
| `project.dispatcher_task_events` | ~5 | task_db, activity_service | Basse |
| `project.dispatcher_task_artifacts` | ~8 | artifact_store, deliverable_service, automation_service | Basse |
| `project.hitl_requests` | ~8 | hitl_bridge, hitl_service, issue_helpers | Basse |
| `project.hitl_users` | ~10 | auth_service, team_service | Basse |
| `project.hitl_team_members` | ~5 | team_service | Basse |
| `project.hitl_chat_messages` | ~3 | chat_service | Basse |
| `project.pm_projects` | ~8 | project_service, pr_service, workflow_service | Basse |
| `project.pm_issues` | ~15 | issue_service, pulse_service, relation_service | Basse |
| `project.pm_issue_counters` | ~3 | issue_service | Basse |
| `project.pm_issue_relations` | ~5 | relation_service | Basse |
| `project.pm_pull_requests` | ~5 | pr_service | Basse |
| `project.pm_inbox` | ~3 | inbox_service | Basse |
| `project.pm_activity` | ~3 | activity_service | Basse |
| `project.rag_documents` | ~5 | rag_service | Basse |
| `project.rag_conversations` | ~3 | analysis_service | Basse |
| `project.automation_rules` | ~5 | automation_service | Basse |
| `project.project_workflows` | ~8 | multi_workflow_service, artifact_store | Basse |
| `project.deliverable_remarks` | ~3 | deliverable_service | Basse |
| **Total** | **~120 occurrences** | **~26 fichiers** | Basse |

**Note** : c'est du SQL brut (asyncpg) — le schema `project.` est fondamental et ne change jamais. Extraire dans des constantes serait du over-engineering. Criticite basse.

---

## 6. Chemins de fichiers en dur

| Fichier | Ligne | Valeur | Devrait etre | Criticite |
|---|---|---|---|---|
| `dispatcher/core/config.py` | 15 | `"/root/ag.flow"` (default) | Env var `AG_FLOW_ROOT` (deja lue) | Moyenne |
| `hitl-new/core/config.py` | ~70 | `"/app/config"`, `"config"` (recherche) | Acceptable — pattern de decouverte | Basse |
| `hitl-new/services/project_type_service.py` | ~25 | `"Shared/Projects"` | Constante `SHARED_PROJECTS_DIR` ou settings | Moyenne |
| `hitl-new/services/workflow_service.py` | ~130 | `"config/Teams"`, `"Shared/Teams"` | Constantes ou settings | Moyenne |

---

## 7. Valeurs par defaut metier en dur

| Fichier | Ligne | Valeur | Description | Devrait etre | Criticite |
|---|---|---|---|---|---|
| `dispatcher/core/config.py` | 17 | `1800` | HITL question timeout (30 min) | `HITL_QUESTION_TIMEOUT` env | Basse |
| `dispatcher/core/config.py` | 13 | `"2g"` | Agent mem limit | `AGENT_MEM_LIMIT` env (deja lue) | Basse |
| `dispatcher/core/config.py` | 14 | `100000` | Agent CPU quota | `AGENT_CPU_QUOTA` env (deja lue) | Basse |
| `dispatcher/core/config.py` | 12 | `"agflow-claude-code:latest"` | Default agent image | `AGENT_DEFAULT_IMAGE` env (deja lue) | Basse |
| `dispatcher/core/database.py` | 27 | `30` | DB command timeout | `settings.db_command_timeout` | Basse |
| `hitl-new/core/database.py` | 26 | `30` | DB command timeout | `settings.db_command_timeout` | Basse |
| `dispatcher/models/schemas.py` | 29 | `300` | Default task timeout | Parametre ou settings | Basse |
| `hitl-new/services/rag_service.py` | ~50 | `1000` | Max tokens per chunk | Constante `MAX_CHUNK_TOKENS` | Basse |
| `hitl-new/services/rag_service.py` | ~50 | `100` | Chunk overlap tokens | Constante `CHUNK_OVERLAP` | Basse |
| `hitl-new/services/rag_service.py` | ~50 | `200` | Min merge threshold | Constante `MIN_MERGE_TOKENS` | Basse |
| `dispatcher/services/docker_manager.py` | 123 | `200` | Logs tail lines | Constante ou settings | Basse |
| `hitl-new/core/config.py` | 26 | `"admin@langgraph.local"` | Admin email default | `HITL_ADMIN_EMAIL` env (deja lue) | Moyenne |
| `hitl-new/core/config.py` | 27 | `"admin"` | Admin password default | `HITL_ADMIN_PASSWORD` env (deja lue) | **HAUTE** (securite) |

---

## 8. Strings UI non-i18n (Frontend)

| Fichier | Ligne | Valeur | Devrait etre | Criticite |
|---|---|---|---|---|
| Aucune string visible non-i18n trouvee | — | — | — | — |

**Le frontend est clean** — toutes les strings visibles passent par `t()`.

### Points mineurs frontend

| Fichier | Ligne | Valeur | Description | Criticite |
|---|---|---|---|---|
| `hitl-frontend/src/components/features/auth/GoogleSignIn.tsx` | 81 | `width: 320` | Largeur bouton Google | Basse |
| `hitl-frontend/src/components/features/project/DependencyGraphSimple.tsx` | ~80 | `#ef4444`, `#6b7280` | Couleurs SVG inline | Basse |
| `hitl-frontend/src/hooks/useWebSocket.ts` | 8-10 | `5000`, `30000`, `10` | Backoff WS (bien nommes en const) | Basse |
| `hitl-frontend/src/api/client.ts` | 1 | `'hitl_token'` | Cle localStorage (bien nommee en const) | Basse |
| `hitl-frontend/src/stores/teamStore.ts` | 13 | `'hitl_active_team'` | Cle localStorage (bien nommee en const) | Basse |

---

## Resume par criticite

| Criticite | Nombre | Exemples |
|---|---|---|
| **HAUTE** | 5 | Credentials DB dans defaults, URL RAG hardcodee, password admin "admin" |
| **MOYENNE** | 10 | Agent ID "project_analyst", canaux PG NOTIFY eparpilles, chemins config |
| **BASSE** | ~130 | Noms de tables SQL, timeouts, constantes bien nommees |

---

## Recommandations

### Priorite 1 (securite)
1. Supprimer les credentials des defaults pydantic-settings (forcer l'env var)
2. Forcer un mot de passe admin non-"admin" au premier demarrage

### Priorite 2 (maintenabilite)
3. Creer `core/channels.py` avec les constantes PG NOTIFY (partage dispatcher + console)
4. Rendre le `agent_id` de l'analyse configurable (parametre ou config workflow)
5. Utiliser `settings.hitl_internal_url` pour l'endpoint RAG au lieu de le hardcoder

### Priorite 3 (nice-to-have)
6. Extraire les constantes RAG (chunk size, overlap) dans settings ou config
7. Centraliser les chemins `Shared/Projects/`, `config/Teams/` dans settings
8. Ajouter un `core/constants.py` pour les patterns de thread_id
