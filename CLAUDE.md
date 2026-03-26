# LandGraph — Instructions Claude Code

## Projet 

Plateforme multi-agent (Python/LangGraph) orchestrant 13 agents IA pour le cycle de vie logiciel.
Stack : FastAPI + PostgreSQL (pgvector) + Redis + Docker Compose, sur Proxmox LXC 110 (Ubuntu 24).

## Commandes essentielles

```bash

# Deploy & Build
bash deploy.sh

# Build
bash build.sh

```

## Navigation du code

**Règle d'or** : `team_resolver.py` est la SOURCE UNIQUE pour résoudre les chemins de fichiers. Ne jamais hardcoder un chemin vers config/.

```
agents/shared/       → Modules partagés (tout le runtime : base_agent, channels, workflow_engine...)
agents/gateway.py    → API FastAPI (point d'entrée)
agents/orchestrator.py → Noeud LangGraph (routing)
config/              → Config racine (teams.json, llm_providers.json, mcp_servers.json)
config/Team1/        → Config équipe (agents_registry.json, Workflow.json, prompts .md)
Shared/              → Catalogue agents, prompts localisés, cultures
hitl/                → Console HITL (server.py + static/)
web/                 → Dashboard admin (server.py + static/)
```

**Pas de fichier Python par agent.** Tous les agents sont définis dans `agents_registry.json` et exécutés via `BaseAgent`. Pour ajouter un agent : ajouter au registry + créer le prompt .md.

## Conventions de code

- **Python 3.11+**, async/await partout (FastAPI + LangGraph sont async)
- **Canaux factorisés** : toujours utiliser `channels.py` (get_default_channel), jamais appeler Discord/SMTP directement
- **Résolution fichiers** : toujours passer par `team_resolver`, jamais de path en dur
- **LLM** : toujours via `llm_provider.py` (factory multi-provider), jamais instancier un ChatAnthropic directement
- **MCP** : config dans `mcp_servers.json` + `agent_mcp_access.json`, jamais hardcoder une commande MCP
- **State** : tout le state LangGraph passe par `state.py`, pas de globals
- **Imports** : les modules shared s'importent avec `from agents.shared.xxx import ...`
- **Logs** : utiliser `logging.getLogger(__name__)`, pas de print()

## Utilisation des outils

### Context7 — documentation live
- **Quand** : AVANT d'écrire du code qui utilise LangGraph, LangChain, FastAPI, Pydantic, ou toute lib externe
- **Pourquoi** : les API évoluent vite, ne te fie pas à ta mémoire pour les signatures, paramètres ou patterns
- **Comment** : interroge Context7 pour la version à jour, puis code en t'appuyant sur la réponse
- Particulièrement critique pour : les StateGraph LangGraph, les tools LangChain, les modèles Pydantic v2, les dépendances FastAPI

### Serena — navigation et compréhension du code
- **Quand** : avant un refactor, pour comprendre les dépendances entre modules, ou pour trouver tous les usages d'une fonction/classe
- **Pourquoi** : plus fiable que grep pour la navigation sémantique (comprend les imports, classes, héritages)
- **Comment** : utilise Serena pour cartographier les impacts avant de proposer un plan de modification
- Cas typiques : "quels modules appellent team_resolver ?", "qui hérite de BaseAgent ?", "où est utilisé workflow_engine.get_deliverables_to_dispatch ?"

### Code review — /review, /pr-review
- **Quand** : avant de me présenter un changement multi-fichiers (>3 fichiers ou >100 lignes)
- **Pourquoi** : détecte les régressions, incohérences et problèmes de style avant que je les voie
- **Comment** : lance /review, corrige les problèmes détectés, puis présente-moi le résultat propre

### Commits — /commit
- **Quand** : quand je demande explicitement de committer (jamais de ta propre initiative)
- **Comment** : message en français, descriptif, format conventionnel

### Security guidance
- **Quand** : si tu modifies du code lié à l'auth (HITL JWT, MCP HMAC, Google OAuth), aux endpoints exposés, ou au .env
- **Pourquoi** : ce projet expose des APIs (gateway 8123, HITL 8090, MCP SSE) — les failles de sécurité sont critiques
- **Comment** : le plugin vérifie automatiquement, mais sois proactif sur les patterns d'auth et de validation d'input

### Memory MCP
- **Quand** : une décision d'architecture importante est prise en session (ex: "on utilise pgvector pour le RAG", "le dispatch se fait par livrable pas par agent")
- **Pourquoi** : complément à LESSONS.md — LESSONS = erreurs corrigées, Memory = décisions prises
- **Ne jamais stocker** : secrets, tokens, mots de passe, données sensibles

### Playwright — tests E2E (quand disponible)
- **Quand** : pour tester les interfaces web (dashboard admin, HITL console) après modification frontend
- **Comment** : naviguer vers les pages modifiées, vérifier que les éléments clés sont présents et fonctionnels

### Qodo — tests unitaires
- **Quand** : après ajout d'une feature ou refactor d'un module Python dans agents/shared/
- **Comment** : générer ou mettre à jour les tests pour le module modifié

## Règles de workflow

### Livraison
- **Ne livre jamais le code ni en test ni sur git sans une demande explicite de ma part**
- Ne modifie pas `.env` sauf si je le demande
- Commit messages en français

### Planification (selon complexité)
- **Fix mineur** (typo, une ligne) : exécute directement
- **Feature / modification** : propose un plan en 3-5 points, attends ma validation
- **Refactor cross-module / nouveau système** : analyse les fichiers concernés, propose un plan détaillé avec la liste des fichiers à modifier, attends ma validation
- **Doute sur l'intention ou le scope** : demande une clarification AVANT de planifier

### Vérification avant validation
Avant de déclarer une tâche terminée :
1. Le code s'exécute sans erreur (lance le build ou le linter)
2. Le cas nominal fonctionne (teste manuellement ou via test)
3. Les imports ajoutés existent réellement dans le projet
4. Pas de régression sur les fichiers modifiés (lance les tests liés)
5. Si modification frontend (hitl/static, web/static) : vérifie que la page charge sans erreur console

Curseur : fix mineur → étapes 1-2 | feature → toutes | refactor → + vérifier les modules dépendants.
**Ne dis jamais "c'est fait" sans avoir exécuté au moins les étapes 1-3.**

### Gestion du contexte
- Avant une exploration large (>5 fichiers) : utilise un subagent Task() et renvoie un résumé structuré
- Après chaque tâche complétée : /clear avant de passer à la suivante
- Si la conversation dépasse ~50% du contexte : /compact manuellement

## Auto-amélioration

Quand je te corrige ou que tu fais une erreur :
- Ajoute une leçon dans `LESSONS.md` à la racine
- Format : `- [module concerné] description courte de l'erreur et de la bonne pratique`
- Relis @LESSONS.md en début de tâche qui touche un module mentionné
- Ne dépasse pas 50 lignes — si le fichier grossit, consolide les leçons similaires

## Documentation de référence

Pour les détails, consulte les docs spécialisées (uniquement quand pertinent pour la tâche) :

- @docs/architecture.md — Stack Docker, services, ports, infra Proxmox
- @docs/gateway-api.md — Endpoints, flux d'un message, thread persistence
- @docs/workflow-engine.md — Phases, parallel groups, dispatch par livrables, catégories
- @docs/agents.md — Registry, champs, hiérarchie routing, BaseAgent
- @docs/channels.md — Interface MessageChannel, implémentations Discord/Email
- @docs/hitl.md — Console HITL, auth locale/Google OAuth, endpoints, rôles
- @docs/llm-providers.md — 17 providers, throttling, override par env
- @docs/mcp.md — Catalogue, lazy install, SSE server, auth HMAC
- @docs/env-vars.md — Variables d'environnement et configuration
- @docs/changelog.md — Historique terminé + roadmap à faire

## Notifications de skills

Quand tu invoques une compétence (skill) via l'outil Skill, affiche systématiquement un marqueur visuel **avant** d'exécuter la skill :

> **`🟢 SKILL`** → _nom-de-la-skill_ — raison en une phrase