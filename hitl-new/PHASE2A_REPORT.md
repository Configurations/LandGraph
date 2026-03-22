# Phase 2a — Wizard projet + Git + RAG — Rapport de fin de phase

> **Date** : 2026-03-22
> **Scope** : hitl-new/ (backend), hitl-frontend/ (frontend), dispatcher/ (modification mineure), scripts/init.sql

---

## 1. Inventaire des fichiers

### Backend — Nouveaux fichiers

| Fichier | Lignes | Role |
|---|---|---|
| `hitl-new/schemas/project.py` | 74 | ProjectCreate, ProjectResponse, GitConfig, GitTestResponse, SlugCheckResponse, GitStatusResponse |
| `hitl-new/schemas/rag.py` | 53 | RagSearchRequest/Response, ConversationMessage, UploadResponse |
| `hitl-new/services/project_service.py` | 136 | CRUD projet, structure disque, fichier .project |
| `hitl-new/services/git_service.py` | 157 | Clone, init, status git via subprocess |
| `hitl-new/services/git_providers.py` | 153 | API GitHub/GitLab/Gitea/Forgejo/Bitbucket (test, create repo) |
| `hitl-new/services/upload_service.py` | 117 | Upload fichiers, extraction texte (MD/TXT/PDF) |
| `hitl-new/services/rag_service.py` | 269 | Chunking, embeddings multi-provider, vectorisation pgvector, recherche |
| `hitl-new/services/analysis_service.py` | 102 | Lancement agent analyse via dispatcher, conversation |
| `hitl-new/routes/projects.py` | 120 | 7 endpoints projet + git |
| `hitl-new/routes/rag.py` | 136 | 7 endpoints RAG + upload + analyse |
| `hitl-new/routes/internal.py` | 19 | 1 endpoint interne RAG (sans auth) |

### Backend — Fichiers modifies

| Fichier | Modification |
|---|---|
| `hitl-new/main.py` | +3 imports + 3 include_router (projects, rag, internal) |
| `hitl-new/core/pg_notify.py` | +2 channels : task_progress, task_artifact |
| `hitl-new/requirements.txt` | +pymupdf==1.24.0 |

### Backend — Tests

| Fichier | Lignes | Tests |
|---|---|---|
| `test_project_service.py` | 144 | 10 |
| `test_git_service.py` | 177 | 7 |
| `test_rag_service.py` | 174 | 10 |
| `test_upload_service.py` | 119 | 7 |
| `test_project_routes.py` | 150 | 8 |
| `test_rag_routes.py` | 154 | 7 |
| **Total backend** | **918** | **49** |

### Frontend — Nouveaux fichiers

| Fichier | Lignes | Role |
|---|---|---|
| `src/api/projects.ts` | 48 | 7 fonctions API projet + git |
| `src/api/rag.ts` | 72 | 7 fonctions API RAG + upload + analyse |
| `src/stores/projectStore.ts` | 60 | Zustand : projects, wizard state |
| `src/components/ui/Stepper.tsx` | 57 | Stepper horizontal reutilisable |
| `src/components/features/project/WizardShell.tsx` | 128 | Container wizard (stepper + nav + steps) |
| `src/components/features/project/WizardStepSetup.tsx` | 103 | Etape 1 : nom + slug + test existence |
| `src/components/features/project/WizardStepGit.tsx` | 127 | Etape 2 : service git + test connexion |
| `src/components/features/project/WizardStepCulture.tsx` | 51 | Etape 3 : selection langue |
| `src/components/features/project/WizardStepDocuments.tsx` | 85 | Etape 4 : upload + vectorisation |
| `src/components/features/project/WizardStepAnalysis.tsx` | 60 | Etape 5 : chat avec agent analyse |
| `src/components/features/project/ProjectCard.tsx` | 58 | Carte projet dans la grille |
| `src/components/features/project/GitStatusBadge.tsx` | 33 | Badge connexion git |
| `src/components/features/project/DocumentList.tsx` | 53 | Liste fichiers uploades |
| `src/components/features/project/DocumentDropzone.tsx` | 65 | Zone drag & drop (react-dropzone) |
| `src/components/features/project/AnalysisChat.tsx` | 84 | Chat avec agent d'analyse |
| `src/pages/ProjectsPage.tsx` | 56 | Page liste projets |
| `src/pages/ProjectWizardPage.tsx` | 21 | Page wizard (wrapper) |

### Frontend — Fichiers modifies

| Fichier | Modification |
|---|---|
| `src/router.tsx` | +2 routes (/projects, /projects/new) |
| `src/components/layout/Sidebar.tsx` | +1 SidebarItem "Projets" avec icone dossier |
| `src/api/types.ts` | +11 interfaces TypeScript |
| `public/locales/fr/translation.json` | +5 groupes de cles (project, git, documents, analysis, wizard) |
| `public/locales/en/translation.json` | Idem en anglais |
| `package.json` | +react-dropzone |

### Frontend — Tests

| Fichier | Lignes | Tests |
|---|---|---|
| `WizardStepSetup.test.tsx` | 69 | 4 |
| `WizardStepGit.test.tsx` | 86 | 5 |
| `DocumentDropzone.test.tsx` | 53 | 3 |
| `ProjectCard.test.tsx` | 47 | 4 |
| `projectStore.test.ts` | 71 | 6 |
| **Total frontend** | **326** | **22** |

### Dispatcher — Modifications

| Fichier | Lignes changees | Modification |
|---|---|---|
| `dispatcher/services/docker_manager.py` | +6 | Param `network` dans create_container + managed_container |
| `dispatcher/services/task_runner.py` | +4 | Passe network=langgraph-net si rag_endpoint dans context |

### SQL

| Fichier | Ajout |
|---|---|
| `scripts/init.sql` | ALTER pm_projects (8 colonnes), CREATE rag_documents (avec vector(1536)), CREATE rag_conversations, index IVFFlat |

### Totaux

| Categorie | Fichiers | Lignes |
|---|---|---|
| Backend nouveau code | 11 | 1336 |
| Backend tests | 6 | 918 |
| Frontend nouveau code | 17 | 1160 |
| Frontend tests | 5 | 326 |
| Dispatcher modifie | 2 | +10 |
| SQL | 1 | +45 |
| **Grand total** | **42 fichiers** | **~3800 lignes** |

---

## 2. Ecarts avec la spec

| Point de la spec | Implementation | Raison |
|---|---|---|
| git_service.py en 1 fichier (~250 lignes) | **Decoupe** en git_service.py (157) + git_providers.py (153) | Respect limite 300 lignes |
| IVFFlat index direct | **Conditionnel** avec try/except | IVFFlat a besoin de donnees pour fonctionner — creation gracieuse |
| types.ts non prevu dans la spec | **Ajoute** | Necessaire pour TypeScript strict (interfaces partagees) |
| Endpoint check-slug en POST | **POST** `/api/projects/{slug}/check-slug` | Le spec disait POST, confirme |
| Dimension embedding configurable | **1536 par defaut** hardcode dans DDL | pgvector ne permet pas de changer la dimension d'une colonne existante — noter pour config future |

---

## 3. Ecarts avec les Phases 0 et 1

| Point | Phase 0/1 | Phase 2a | Alignement |
|---|---|---|---|
| dispatcher docker_manager.py | `NetworkMode: "none"` (hardcode) | Param `network` optionnel | Retrocompat : None → "none" |
| dispatcher task_runner.py | Pas de logic reseau | Passe `network="langgraph-net"` si `rag_endpoint` dans context | Transparent pour les taches existantes |
| pg_notify.py | 2 channels (hitl_request, hitl_response) | +2 channels (task_progress, task_artifact) | Ajout non destructif |
| pm_projects table | Colonnes existantes (name, description, lead, team_id, color, status, etc.) | +8 colonnes via ALTER ADD IF NOT EXISTS | Retrocompat, pas de suppression |
| Routes main.py | 5 routers montes | +3 routers (projects, rag, internal) | Ajout non destructif |

---

## 4. Schemas et contrats d'API reels

### POST /api/projects
```
Request:  ProjectCreate { name, slug, team_id, language, git_service, git_url, git_login, git_token, git_repo_name }
Response: ProjectResponse { id, name, slug, team_id, language, git_service, git_url, git_login, git_repo_name, status, color, created_at, updated_at }
Errors:   409 { key: "project.slug_exists" }
```

### GET /api/projects
```
Query:    ?team_id= (optionnel)
Response: ProjectResponse[]
```

### GET /api/projects/{slug}
```
Response: ProjectResponse
Errors:   404 { key: "project.not_found" }
```

### POST /api/projects/{slug}/check-slug
```
Response: SlugCheckResponse { exists: bool, path: str }
```

### POST /api/projects/{slug}/git/test
```
Request:  GitConfig { service, url, login, token, repo_name }
Response: GitTestResponse { connected: bool, repo_exists: bool, message: str }
```

### POST /api/projects/{slug}/git/init
```
Request:  GitConfig
Response: { ok: true }
Errors:   500 { key: "git.init_failed" }
```

### GET /api/projects/{slug}/git/status
```
Response: GitStatusResponse { branch, clean, ahead, behind }
```

### POST /api/projects/{slug}/upload
```
Request:  multipart/form-data (file)
Response: UploadResponse { filename, size, content_type, chunks_indexed }
```

### GET /api/projects/{slug}/uploads
```
Response: UploadedFile[] { name, size, content_type }
```

### DELETE /api/projects/{slug}/uploads/{filename}
```
Response: { ok: true }
```

### POST /api/projects/{slug}/search
```
Request:  RagSearchRequest { project_slug, query, top_k: 5 }
Response: RagSearchResponse { results: RagSearchResult[] { content, filename, chunk_index, score, metadata } }
```

### POST /api/projects/{slug}/analysis/start
```
Request:  { team_id: str }
Response: { task_id: str } | { error: "dispatcher_unavailable" }
```

### GET /api/projects/{slug}/analysis/status
```
Query:    ?task_id=UUID
Response: TaskDetailResponse (proxy depuis dispatcher)
```

### GET /api/projects/{slug}/analysis/conversation
```
Response: ConversationMessage[] { id, project_slug, task_id, sender, content, created_at }
```

### POST /api/internal/rag/search (sans auth)
```
Request:  RagSearchRequest { project_slug, query, top_k }
Response: RagSearchResponse { results: [...] }
```

---

## 5. Composants React reels

| Composant | Props |
|---|---|
| `Stepper` | steps ({labelKey, completed}[]), activeStep (number), onStepClick?, className? |
| `WizardShell` | (no props — uses projectStore) |
| `WizardStepSetup` | (no props — uses projectStore) |
| `WizardStepGit` | (no props — uses projectStore) |
| `WizardStepCulture` | (no props — uses projectStore) |
| `WizardStepDocuments` | (no props — uses projectStore.wizardData.slug) |
| `WizardStepAnalysis` | (no props — uses projectStore) |
| `ProjectCard` | project (ProjectResponse), className? |
| `GitStatusBadge` | connected (bool), repoExists (bool), className? |
| `DocumentList` | files ({name, size, content_type}[]), onDelete?(filename), className? |
| `DocumentDropzone` | onUpload(file: File), uploading (bool), className? |
| `AnalysisChat` | slug (string), taskId (string\|null), className? |
| `ProjectsPage` | (page — no props) |
| `ProjectWizardPage` | (page — no props) |

---

## 6. Nouvelles cles i18n

### Frontend (public/locales/)

```
project: projects, new_project, name, slug, slug_available, slug_exists, slug_checking,
         culture, create, created_success, no_projects, no_projects_desc
git: service, url, login, token, repo_name, test_connection, connected, connection_error,
     repo_exists_warning, repo_not_found, creating_repo, cloning_repo, other, status
documents: upload, dropzone, accepted_formats, uploading, vectorizing, delete_confirm
analysis: title, starting, chat_placeholder, agent_thinking, complete
wizard: step_setup, step_git, step_culture, step_documents, step_analysis, next, previous, skip
```

### Backend (i18n/)

```
project.slug_exists, project.not_found, project.create_failed
git.connection_failed, git.unsupported_service, git.init_failed, git.clone_failed
rag.no_embedding_provider, rag.embedding_failed, rag.index_failed
```

---

## 7. Etat des tests

| Categorie | Tests | Etat |
|---|---|---|
| Backend (test_project_service) | 10 | Non execute |
| Backend (test_git_service) | 7 | Non execute |
| Backend (test_rag_service) | 10 | Non execute |
| Backend (test_upload_service) | 7 | Non execute |
| Backend (test_project_routes) | 8 | Non execute |
| Backend (test_rag_routes) | 7 | Non execute |
| Frontend (WizardStepSetup) | 4 | Non execute |
| Frontend (WizardStepGit) | 5 | Non execute |
| Frontend (DocumentDropzone) | 3 | Non execute |
| Frontend (ProjectCard) | 4 | Non execute |
| Frontend (projectStore) | 6 | Non execute |
| **Total Phase 2a** | **71** | Tests unitaires avec mocks |

**Total cumule Phases 1+2a** : 178 tests (38+69+71)

---

## 8. Modification du dispatcher

### `dispatcher/services/docker_manager.py`

Ajout du parametre `network: Optional[str] = None` a `create_container()` et `managed_container()` :
- Si `network` est fourni → `"NetworkMode": network` (ex: `"langgraph-net"`)
- Si `network` est None → `"NetworkMode": "none"` (comportement inchange)

### `dispatcher/services/task_runner.py`

Dans `_execute()`, avant `managed_container()` :
```python
network = None
if task.payload.context.get("rag_endpoint"):
    network = "langgraph-net"
```

Le parametre `network` est passe a `managed_container()`. **Aucun impact sur les taches existantes** (sans rag_endpoint → network reste None → isolation preservee).

---

## 9. Points d'attention pour la Phase 2b

### Livrables et validation

1. **dispatcher_task_artifacts** : la console devra UPDATE `status` (pending→approved/rejected), `reviewer`, `review_comment`, `reviewed_at` quand un humain valide un livrable
2. **Copie vers repo** : apres approbation, copier le fichier de `docs/{team}/{workflow}/...` vers `repo/docs/{categorie}/{sous-categorie}/` et git commit
3. **Categories workflow** : le champ `category` dans dispatcher_task_artifacts correspond aux categories definies dans Workflow.json (Phase 0 categories feature)

### Chat agents

1. **hitl_chat_messages** : table existante, trigger PG NOTIFY `hitl_chat`
2. **WebSocket** : deja prepare dans pg_notify.py — ajouter le handler pour `hitl_chat`
3. **Interface** : conversation agent ↔ humain dans un panel coulissant

### Branching git

1. L'agent code dans une branche `temp/{agent_id}/{task_id}`
2. Le dispatcher verifie l'existence de la branche apres execution
3. La console doit pouvoir afficher les branches, les diffs, et creer des PRs

### Provider d'embeddings

1. **Non configure sur AGT1** — il faudra ajouter un provider dans `config/llm_providers.json`
2. Le code RAG supporte OpenAI, Ollama, Azure — mais aucun n'est active
3. Pour tester le RAG, configurer au minimum Ollama (nomic-embed-text) ou OpenAI

### Structure du store

1. `projectStore` expose `activeSlug` et `wizardData` — la Phase 2b peut les reutiliser
2. Le `teamStore.activeTeamId` est utilise par les filtres de la liste projets
3. Ajouter un `deliverableStore` pour la gestion des livrables en Phase 2b

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
