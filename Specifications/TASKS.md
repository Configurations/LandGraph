# Plan d'implémentation — Application de Gestion de Production (HITL)

> Analyse des écarts entre l'existant (`hitl/`) et les spécifications (`Specifications.md`)

---

## Ce qui existe et sera réutilisé

| Composant | Usage |
|-----------|-------|
| Auth JWT + Google OAuth | Conservé tel quel (server.py) |
| Multi-équipes (teams.json) | Conservé, alimente la sidebar Teams |
| WebSocket + PG LISTEN/NOTIFY | Étendu pour les nouvelles notifications |
| Gateway /invoke | Utilisé pour l'AI Planning (création de projet) |
| Chat agents | Conservé comme fonctionnalité existante |
| HITL questions (inbox existant) | Migré vers le nouvel Inbox comme type de notification |
| Base de données PostgreSQL | Nouvelles tables ajoutées |

---

## Phase 1 — Base de données (nouvelles tables)

### T1.1 — Table `project.pm_projects`
```sql
CREATE TABLE project.pm_projects (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  lead TEXT NOT NULL,
  team_id TEXT NOT NULL,
  color TEXT DEFAULT '#6366f1',
  status TEXT DEFAULT 'on-track',  -- on-track | at-risk | off-track
  start_date DATE,
  target_date DATE,
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### T1.2 — Table `project.pm_issues`
```sql
CREATE TABLE project.pm_issues (
  id TEXT PRIMARY KEY,              -- "ENG-421"
  project_id INTEGER REFERENCES project.pm_projects(id),
  title TEXT NOT NULL,
  description TEXT DEFAULT '',
  status TEXT DEFAULT 'backlog',    -- backlog | todo | in-progress | in-review | done
  priority INTEGER DEFAULT 3,       -- 1=critique, 2=haute, 3=moyenne, 4=basse
  assignee TEXT,
  team_id TEXT NOT NULL,
  tags TEXT[] DEFAULT '{}',
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pm_issues_project ON project.pm_issues(project_id);
CREATE INDEX idx_pm_issues_status ON project.pm_issues(status);
CREATE INDEX idx_pm_issues_team ON project.pm_issues(team_id);
```

### T1.3 — Table `project.pm_issue_relations`
```sql
CREATE TABLE project.pm_issue_relations (
  id SERIAL PRIMARY KEY,
  type TEXT NOT NULL,                -- blocks | relates-to | parent | duplicates
  source_issue_id TEXT NOT NULL REFERENCES project.pm_issues(id) ON DELETE CASCADE,
  target_issue_id TEXT NOT NULL REFERENCES project.pm_issues(id) ON DELETE CASCADE,
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(type, source_issue_id, target_issue_id)
);
```
Note : `blocked-by` et `sub-task` sont déduits automatiquement (inverse de `blocks` et `parent`).

### T1.4 — Table `project.pm_pull_requests`
```sql
CREATE TABLE project.pm_pull_requests (
  id TEXT PRIMARY KEY,              -- "PR-251"
  title TEXT NOT NULL,
  author TEXT NOT NULL,
  issue_id TEXT REFERENCES project.pm_issues(id),
  status TEXT DEFAULT 'draft',      -- pending | approved | changes_requested | draft
  additions INTEGER DEFAULT 0,
  deletions INTEGER DEFAULT 0,
  files INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### T1.5 — Table `project.pm_inbox`
```sql
CREATE TABLE project.pm_inbox (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES project.hitl_users(id),
  type TEXT NOT NULL,               -- mention | assign | comment | status | review | blocked | unblocked | dependency_added
  text TEXT NOT NULL,
  issue_id TEXT,
  related_issue_id TEXT,
  relation_type TEXT,
  avatar TEXT,
  read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pm_inbox_user ON project.pm_inbox(user_id, read, created_at DESC);
```

### T1.6 — Table `project.pm_activity`
```sql
CREATE TABLE project.pm_activity (
  id SERIAL PRIMARY KEY,
  project_id INTEGER REFERENCES project.pm_projects(id),
  user_name TEXT NOT NULL,
  action TEXT NOT NULL,
  issue_id TEXT,
  detail TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pm_activity_project ON project.pm_activity(project_id, created_at DESC);
```

### T1.7 — Table `project.pm_project_members`
```sql
CREATE TABLE project.pm_project_members (
  project_id INTEGER REFERENCES project.pm_projects(id) ON DELETE CASCADE,
  user_name TEXT NOT NULL,
  role TEXT DEFAULT 'member',       -- lead | member
  PRIMARY KEY(project_id, user_name)
);
```

### T1.8 — Trigger NOTIFY pour les nouvelles notifications inbox
```sql
CREATE OR REPLACE FUNCTION notify_pm_inbox() ...
-- PG NOTIFY 'pm_inbox_channel' on INSERT
```

---

## Phase 2 — Backend API (endpoints FastAPI)

### T2.1 — CRUD Projects
- `GET /api/pm/projects` — Liste des projets (avec stats calculées : progress, blockedCount, blockingCount)
- `POST /api/pm/projects` — Créer un projet
- `GET /api/pm/projects/{id}` — Détail projet (avec members, issue stats, velocity)
- `PUT /api/pm/projects/{id}` — Modifier projet
- `DELETE /api/pm/projects/{id}` — Supprimer projet

### T2.2 — CRUD Issues
- `GET /api/pm/issues` — Liste globale (avec filtres team, status, assignee, project)
- `POST /api/pm/issues` — Créer une issue (auto-génère l'ID : `{TEAM}-{seq}`)
- `GET /api/pm/issues/{id}` — Détail issue (avec relations calculées)
- `PUT /api/pm/issues/{id}` — Modifier issue (status, priority, assignee, tags)
- `DELETE /api/pm/issues/{id}` — Supprimer issue

### T2.3 — Relations (dépendances)
- `GET /api/pm/issues/{id}/relations` — Relations d'une issue
- `POST /api/pm/issues/{id}/relations` — Ajouter une relation
- `DELETE /api/pm/relations/{rel_id}` — Supprimer une relation
- Logique : créer `blocks A→B` crée implicitement le `blocked-by B→A` (pas stocké, déduit)

### T2.4 — Pull Requests
- `GET /api/pm/reviews` — Liste PRs (avec filtres)
- `POST /api/pm/reviews` — Créer une PR
- `PUT /api/pm/reviews/{id}` — Modifier PR

### T2.5 — Inbox (notifications)
- `GET /api/pm/inbox` — Notifications de l'utilisateur courant
- `PUT /api/pm/inbox/{id}/read` — Marquer comme lu
- `PUT /api/pm/inbox/read-all` — Marquer tout comme lu
- Helper interne : `create_notification(user_id, type, text, issue_id, ...)` appelé par les autres endpoints

### T2.6 — Activity
- `GET /api/pm/projects/{id}/activity` — Timeline d'activité du projet
- Helper interne : `log_activity(project_id, user, action, issue_id, detail)` appelé automatiquement

### T2.7 — Pulse (métriques)
- `GET /api/pm/pulse` — Métriques globales (velocity, burndown, cycle time, throughput, status distribution, team activity, dependency health)
- Calculé à la volée depuis les tables pm_issues, pm_issue_relations, pm_activity

### T2.8 — AI Planning (création projet assistée par IA)
- `POST /api/pm/ai/plan` — Envoie la description du projet au gateway `/invoke` avec l'orchestrateur/planner, retourne les issues et dépendances générées
- Utilise le même pattern que le chat agent existant

### T2.9 — Séquence d'ID auto (issue counter par team)
- Fonction SQL ou logique Python pour générer `ENG-001`, `ENG-002`, etc.
- Table `project.pm_issue_counters(team_id TEXT PRIMARY KEY, next_seq INTEGER DEFAULT 1)`

---

## Phase 3 — Frontend CSS (refonte design tokens)

### T3.1 — Nouveaux design tokens
Ajouter les CSS variables de la spec (palette Linear dark) tout en conservant la compatibilité existante :
```css
--bg-primary: #0a0a0c
--bg-secondary: #111114
--bg-tertiary: #1a1a1f
--bg-hover: #1e1e24
--bg-active: #24242c
--border-subtle: #222228
--border-strong: #2e2e36
--text-primary: #e8e8ec
--text-secondary: #9898a4
--text-tertiary: #6b6b78
--text-quaternary: #45454f
--accent-blue: #5b8def
--accent-green: #3ecf8e
--accent-orange: #f0a050
--accent-yellow: #e8c44a
--accent-red: #ef5555
--accent-purple: #a78bfa
```

### T3.2 — Typographie monospace
Police pile : SF Mono, Fira Code, JetBrains Mono, Cascadia Code, monospace. Base 13px.

### T3.3 — Animations
```css
@keyframes fadeSlideIn { from { opacity: 0; transform: translateY(6px); } to { ... } }
@keyframes slideIn { from { transform: translateX(20px); opacity: 0; } to { ... } }
```
Stagger en cascade (60-80ms entre éléments).

### T3.4 — Composants CSS
- Sidebar (220px / 52px collapsed)
- Header bar (46px)
- Cards, tags, badges, status dots
- Issue rows, group headers (sticky)
- Detail panel (340px / 320px)
- Modal overlay
- Stacked progress bar
- Timeline (trait vertical + dots)

---

## Phase 4 — Frontend HTML (structure SPA)

### T4.1 — Restructurer index.html
- Sidebar gauche (workspace header, search, navigation, workspace, teams, user)
- Zone contenu (header bar + zone de vue)
- Container pour chaque écran (inbox, issues, reviews, pulse, projects)
- Container pour project-detail et create-project-flow
- Conserver les écrans existants (login, register)

---

## Phase 5 — Frontend JS (écrans)

### T5.1 — Sidebar & Navigation
- Toggle collapsed/expanded
- Items : Inbox (badge), Issues, Reviews, Pulse
- Section Workspace : Projects
- Section Teams : liste des équipes avec pastilles
- Utilisateur courant en bas
- État actif avec highlight

### T5.2 — Écran Inbox (notifications)
- Onglets : All, Mentions, Assigned, Reviews
- Liste notifications avec animation cascade
- Indicateur non-lu (point bleu)
- Avatar, texte, timestamp
- Opacité 60% si lu
- Types : mention, assign, comment, status, review, blocked, unblocked, dependency_added

### T5.3 — Écran Issues
- Onglets groupement : status, team, assignee, dependency
- Liste groupée avec headers sticky
- Ligne d'issue : PriorityBadge, ID, StatusIcon, DependencyIndicator, titre, tags, avatar, temps
- Panneau de détail (340px) : titre, bannière blocage, propriétés, tags, section dépendances
- Groupement dependency : Blocked, Blocking others, No dependencies

### T5.4 — Écran Reviews
- Onglets : All PRs, Needs Review, Approved, Drafts
- Ligne PR : avatar, ID+titre, auteur•issue•fichiers, diff summary, badge statut

### T5.5 — Écran Pulse
- Grille 4 métriques (Velocity, Burndown, Cycle Time, Throughput) avec sparklines
- Status Distribution (barre empilée + légende)
- Team Activity (progress bars par membre)
- Dependency Health (métriques + bottlenecks)

### T5.6 — Écran Projects (grille)
- Grille 2 colonnes
- Carte projet : pastille couleur, nom, badge statut, barre progression, indicateurs dépendances, footer (lead avatar + sparkline)
- Clic → Project Detail
- Bouton "+" → Create Project Flow

### T5.7 — Écran Project Detail
- Header fixe : breadcrumb, pastille, nom, badge, métadonnées (lead, dates, membres, badges blocked/blocking)
- Workflow Pipeline (barre 5 segments)
- Onglets : Issues, Dependencies, Team, Activity

### T5.7.1 — Onglet Issues (Project Detail)
- Comme l'écran Issues global mais filtré par projet
- Même panneau de détail avec dépendances

### T5.7.2 — Onglet Dependencies (Project Detail)
- Graphe SVG avec colonnes par status
- Nœuds rectangulaires avec ID + titre tronqué
- Arêtes Bézier cubiques (blocks = trait plein rouge, autres = pointillé)
- Légende

### T5.7.3 — Onglet Team (Project Detail)
- Carte par membre : avatar, nom, rôle, ratio complétion, barre progression, liste issues, indicateur blocage

### T5.7.4 — Onglet Activity (Project Detail)
- Timeline verticale : trait, points bleus, événements (user, action, issue, détail, timestamp)

### T5.8 — Create Project Flow (3 étapes)
- Stepper dans le header (Setup → AI Planning → Review)

### T5.8.1 — Étape Setup
- Formulaire centré (520px) : nom projet, sélection team (3 cartes), dates
- Bouton "Continue with AI Planning" (actif si nom+team remplis)
- Lien "Skip and create empty project"

### T5.8.2 — Étape AI Planning
- Zone de chat (bulles IA/utilisateur) + panneau prévisualisation (300px)
- Header chat avec avatar IA gradient
- Bulle IA : texte + bloc issues générées + relations
- Typing indicator (3 points animés)
- Barre input + navigation (Back to Setup / Review & Create)
- Appelle le gateway `/invoke` avec le planner agent
- Panneau preview : nom, team, description, mini pipeline, dépendances

### T5.8.3 — Étape Review
- Résumé projet (nom, description, team, dates, compteurs)
- Table issues avec flags blocage
- Table dépendances (source → blocks → cible + raison)
- Boutons "Back to AI" + "Create Project"

### T5.9 — Composants partagés JS
- `StatusIcon(status)` — SVG inline par status
- `PriorityBadge(level)` — 4 barres verticales
- `Avatar(name, size)` — Cercle coloré + initiales
- `Tag(label, color)` — Pill compact
- `Sparkline(data, color, width, height)` — SVG polyline
- `ProgressBar(value, color)` — Barre horizontale
- `DependencyIndicator(blockedByCount, blockingCount)` — Pills cadenas/warning
- `RelationTypeBadge(type)` — Badge relation coloré

---

## Phase 6 — Intégration agents (/Agents)

### T6.1 — Endpoint AI Planning → gateway /invoke
- Le chat AI Planning envoie le brief au planner/orchestrator via POST /invoke
- L'agent retourne un JSON structuré avec issues[] et relations[]
- Le frontend parse et affiche dans la bulle IA

### T6.2 — Création effective du projet
- "Create Project" (étape Review) → POST /api/pm/projects + POST /api/pm/issues (bulk) + POST /api/pm/issue_relations (bulk)
- Navigue vers Project Detail du nouveau projet

---

## Phase 7 — Tests unitaires

### T7.1 — Tests API Projects (CRUD, validation, permissions)
### T7.2 — Tests API Issues (CRUD, auto-ID, filtres, dépendances calculées)
### T7.3 — Tests API Relations (création, inverse implicite, suppression cascade)
### T7.4 — Tests API Pull Requests (CRUD, filtres)
### T7.5 — Tests API Inbox (notifications, read/unread, filtres)
### T7.6 — Tests API Activity (log automatique, timeline)
### T7.7 — Tests API Pulse (calculs métriques)
### T7.8 — Tests logique blocage (isBlocked calculé, chaînes transitives)
### T7.9 — Tests AI Planning (mock gateway, parsing réponse)
### T7.10 — Tests séquence ID issues (compteur par team)

---

## Ordre d'exécution

1. **Phase 1** — DB tables + migration SQL
2. **Phase 2** — Backend API endpoints
3. **Phase 7** — Tests unitaires (en parallèle avec Phase 2)
4. **Phase 3** — CSS refonte
5. **Phase 4** — HTML structure
6. **Phase 5** — JS écrans (dans l'ordre : composants → sidebar → inbox → issues → reviews → pulse → projects → project-detail → create-flow)
7. **Phase 6** — Intégration agents

---

## Contraintes

- Tout le code frontend est en vanilla JS (pas de React) — les JSX des specs sont des **maquettes de référence**, pas du code à exécuter
- Le backend reste un seul fichier `server.py` FastAPI
- Les tables utilisent le schema `project.` existant
- L'auth existante (JWT) protège tous les nouveaux endpoints
- Les interactions agents passent par le gateway existant (`/invoke`)
