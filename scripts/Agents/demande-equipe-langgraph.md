# Demande de Construction d'Équipe Multi-Agent LangGraph

> **Instructions** : Copie le contenu du fichier `agent-profile-architect-prompt.md` comme **System Prompt**, puis colle cette demande comme **message utilisateur** dans une nouvelle conversation.

---

## Contexte du projet

Je construis un système multi-agent de gestion de projet de A à Z, hébergé sur un serveur Proxmox (VM Ubuntu 24.04, Docker Compose). L'infrastructure est déjà en place :

- **Orchestration** : LangGraph (StateGraph) avec checkpointer PostgreSQL
- **LLMs** : Claude Sonnet 4.5 (agents spécialisés) + Claude Opus 4.5 (orchestrateur + architecte)
- **Infrastructure** : PostgreSQL 16 + pgvector, Redis 7, Docker Compose
- **Outils** : MCP Protocol (GitHub, Notion, Slack, Filesystem, PostgreSQL)
- **Communication** : Discord MCP Server (notifications, human-in-the-loop, commandes)
- **Observabilité** : Langfuse self-hosted
- **State** : ProjectState partagé via LangGraph checkpointer Postgres

Le système gère deux types de projets :
1. **Web Apps** — React/Next.js + Python/FastAPI + PostgreSQL
2. **Mobile Apps** — React Native + Python/FastAPI + PostgreSQL

Les deux profils partagent le même backend/API.

---

## L'équipe complète — 11 agents à profiler

Génère le **profil complet** (identité, LLM, system prompt, tools MCP, inputs/outputs, state contribution, métriques d'évaluation, escalade, code squelette) pour chacun des 11 agents suivants.

### Agent 1 — 🎯 Orchestrateur (Meta-Agent PM)

- **Rôle** : Cerveau central du système. Il gère le cycle de vie du projet à travers ses phases (Discovery → Design → Build → Ship → Iterate). Il ne fait pas le travail lui-même : il route les tâches vers le bon agent, gère les transitions de phase, et décide quand impliquer l'humain via Discord.
- **Pattern** : Supervisor
- **LLM** : Claude Opus 4.5 (raisonnement complexe pour le routing)
- **Particularités** : 
  - Chaque transition de phase passe par un human gate Discord (#human-review)
  - Il maintient un seuil de confiance (0.0-1.0) — en dessous de 0.7, escalade automatique
  - Il peut déclencher des agents en parallèle quand les tâches sont indépendantes
  - Il envoie des notifications dans Discord (#orchestrateur-logs) à chaque décision
- **State** : Il lit et écrit TOUS les champs du ProjectState
- **Interactions** : Il reçoit de et envoie vers TOUS les autres agents

### Agent 2 — 📋 Analyste (Requirements Agent)

- **Rôle** : Transforme les besoins vagues en spécifications structurées. Il pose les bonnes questions (via Discord si besoin), détecte les ambiguïtés, et produit des user stories INVEST-compliant avec des critères d'acceptation clairs.
- **Pattern** : RAG + Prompt Chains
- **LLM** : Claude Sonnet 4.5
- **Particularités** :
  - Pipeline : brief initial → questions de clarification → PRD structuré → user stories → critères d'acceptation → matrice de priorisation (MoSCoW)
  - Utilise le RAG (Weaviate) pour récupérer des PRDs passés et des templates
  - Produit des user stories au format "En tant que [persona], je veux [action], afin de [bénéfice]"
  - Détecte les exigences non-fonctionnelles implicites (performance, sécurité, accessibilité)
  - Peut poser des questions à l'humain via Discord (#commandes) si le brief est trop ambigu
- **Tools MCP** : Notion (lecture/écriture des specs), Discord (questions de clarification)
- **Inputs** : Brief initial, feedback stakeholders, contraintes business
- **Outputs** : PRD structuré, User Stories, Critères d'acceptation, Matrice de priorisation

### Agent 3 — 🎨 Designer UX/Ergonome (UI/UX & Ergonomics Agent)

- **Rôle** : Conçoit l'expérience utilisateur en appliquant les principes d'ergonomie cognitive et d'accessibilité. Il pense USAGE avant ESTHÉTIQUE. Il transforme les user stories en parcours utilisateur, wireframes, mockups et design system.
- **Pattern** : Plan-and-Execute + Reflection
- **LLM** : Claude Sonnet 4.5
- **Particularités** :
  - Expertise en ergonomie cognitive : heuristiques de Nielsen, loi de Fitts (taille/distance des éléments interactifs), loi de Hick (réduire le nombre de choix), loi de Miller (7±2 éléments)
  - Accessibilité WCAG 2.2 : contrastes, navigation clavier, lecteurs d'écran, responsive
  - Produit des wireframes basse fidélité PUIS des mockups haute fidélité (HTML/CSS/SVG)
  - Génère et maintient un design system (tokens JSON : couleurs, typo, spacing, composants)
  - Intervient DEUX FOIS : en Design (maquettes) et en Build (audit ergonomique du code produit par les devs)
  - Chaque choix de design est annoté avec sa justification ergonomique
- **Tools MCP** : Filesystem (écriture des wireframes/mockups HTML), GitHub (commit des design tokens)
- **Inputs** : User Stories, personas, contraintes d'accessibilité
- **Outputs** : User flows annotés, Wireframes, Mockups (HTML/CSS), Design tokens (JSON), Rapport d'accessibilité, Audit ergonomique (feedback loop vers le Développeur)

### Agent 4 — 🏗️ Architecte (Design Agent)

- **Rôle** : Conçoit l'architecture technique du projet. Il choisit la stack, modélise les données, définit les APIs, et produit des ADRs (Architecture Decision Records) justifiant chaque choix.
- **Pattern** : ReAct + Tool Use
- **LLM** : Claude Opus 4.5 (raisonnement long pour les décisions d'architecture)
- **Particularités** :
  - Produit des diagrammes C4 (contexte, containers, composants) en Mermaid.js
  - Génère des specs OpenAPI 3.1 pour toutes les APIs
  - Chaque décision architecturale est documentée dans un ADR (contexte, options, décision, conséquences)
  - Prend en compte les maquettes du Designer pour adapter les composants techniques
  - Analyse le codebase existant via GitHub MCP si c'est une évolution
  - Pense scalabilité, sécurité et maintenabilité
- **Tools MCP** : GitHub (analyse du code existant), Filesystem (écriture des ADRs et schémas)
- **Inputs** : PRD, User Stories, Maquettes du Designer, Contraintes techniques, Stack existante
- **Outputs** : ADRs, Diagrammes C4 (Mermaid), Specs OpenAPI, Data Models, Choix de stack argumentés

### Agent 5 — 📅 Planificateur (Planning Agent)

- **Rôle** : Décompose le projet en sprints, tâches et milestones. Il estime les efforts à partir de l'historique des projets précédents, identifie le chemin critique et gère les dépendances inter-tâches.
- **Pattern** : Plan-and-Execute
- **LLM** : Claude Sonnet 4.5
- **Particularités** :
  - Décomposition en WBS (Work Breakdown Structure) puis en tâches assignables
  - Estimation via retrieval de l'historique projet (RAG sur les estimations passées)
  - Calcul du chemin critique (algorithme CPM) et détection des dépendances circulaires
  - Génère des sprint backlogs avec les dépendances entre tâches
  - Chaque tâche est tagguée avec l'agent responsable (Frontend, Backend, Mobile, QA, etc.)
  - Produit un risk register avec les risques identifiés et les mitigations
- **Tools MCP** : Linear ou Jira (création des issues/sprints), Notion (roadmap)
- **Inputs** : Architecture, User Stories, Maquettes, Capacité équipe, Deadlines
- **Outputs** : Sprint Backlog, Roadmap, Dépendances, Risk Register, Estimations

### Agent 6 — ⚡ Lead Dev (Supervisor / Coding Agent)

- **Rôle** : Reçoit les tâches de développement du sprint et les dispatche vers le bon sous-agent spécialisé. Il ne code PAS lui-même (sauf pour de la glue code inter-composants). Il analyse chaque tâche, détermine les spécialités nécessaires, peut lancer des sous-agents en parallèle, et consolide les résultats.
- **Pattern** : Supervisor (spawne des sous-agents)
- **LLM** : Claude Sonnet 4.5
- **Particularités** :
  - Analyse chaque tâche et la route vers : Dev Frontend Web, Dev Backend/API, ou Dev Mobile
  - Si une tâche est multi-stack (ex: formulaire + endpoint), il lance les sous-agents en parallèle
  - Fait la review croisée : vérifie que le code frontend consomme correctement l'API backend
  - Consolide les PRs des sous-agents en une PR cohérente
  - Maintient les conventions de code (linting rules, naming conventions, structure de fichiers)
  - Escalade vers l'humain si un conflit de merge ou une décision d'architecture émerge

  **Sous-agent 6a — 🌐 Dev Frontend Web**
  - Stack : React, Next.js, TypeScript, Tailwind CSS, Zustand/Redux
  - Consomme les design tokens et mockups du Designer UX
  - Produit des composants accessibles (WCAG 2.2)
  - Tests : Vitest + Playwright
  - Tools MCP : GitHub, Filesystem

  **Sous-agent 6b — 🔧 Dev Backend/API**
  - Stack : Python, FastAPI, SQLAlchemy, Alembic (migrations), PostgreSQL
  - Implémente les specs OpenAPI générées par l'Architecte
  - Gère l'authentification (JWT/OAuth), la validation (Pydantic), les migrations DB
  - Tests : Pytest + couverture
  - Tools MCP : GitHub, Filesystem, PostgreSQL

  **Sous-agent 6c — 📱 Dev Mobile**
  - Stack : React Native, TypeScript, Expo, React Navigation
  - Adapte les maquettes du Designer pour mobile (responsive, gestures, navigation native)
  - Consomme la même API backend que le Frontend Web
  - Tests : Jest + Detox (E2E)
  - Tools MCP : GitHub, Filesystem

- **Inputs** : Tâches du sprint, Architecture, Maquettes, Code existant, Feedback review
- **Outputs** : Code source, Tests unitaires, Pull Requests, Documentation inline

### Agent 7 — 🔍 QA (Testing Agent)

- **Rôle** : Valide la qualité du code produit. Il génère des tests à partir des critères d'acceptation, exécute les suites, identifie les régressions, mesure la couverture, et produit un verdict Go/No-Go.
- **Pattern** : ReAct + Sandbox Execution
- **LLM** : Claude Sonnet 4.5
- **Particularités** :
  - Génère des tests à partir des critères d'acceptation des user stories
  - Exécute les tests dans un sandbox Docker isolé
  - Vérifie la couverture de code (seuil minimum configurable, ex: 80%)
  - Teste l'accessibilité (axe-core pour le frontend)
  - Peut demander au Designer de valider visuellement si un doute ergonomique survient
  - Produit un rapport structuré : tests passés/échoués, couverture, régressions, recommandations
  - Verdict final : Go (déploiement autorisé) ou No-Go (retour au Lead Dev avec les bugs)
- **Tools MCP** : GitHub (lecture du code, commentaires sur les PRs), Filesystem
- **Inputs** : Code source, Critères d'acceptation, Test plans, Historique bugs
- **Outputs** : Rapports de test, Bug reports, Métriques qualité, Verdict Go/No-Go

### Agent 8 — 🚀 DevOps (Infra Agent)

- **Rôle** : Gère le pipeline CI/CD, l'infrastructure as code, le monitoring et les déploiements. Il automatise tout ce qui peut l'être.
- **Pattern** : Tool Use + Shell Execution
- **LLM** : Claude Sonnet 4.5 (via Claude Code pour l'exécution shell)
- **Particularités** :
  - Génère et maintient les pipelines GitHub Actions
  - Écrit l'Infrastructure as Code (Terraform/Pulumi)
  - Gère les Dockerfiles et docker-compose pour chaque environnement (dev, staging, prod)
  - Configure le monitoring (Grafana + Prometheus) et l'alerting
  - Exécute les déploiements et vérifie les health checks post-deploy
  - Rollback automatique si les health checks échouent
  - Notifie via Discord (#deployments) le statut de chaque déploiement
- **Tools MCP** : GitHub (pipelines, secrets), Filesystem (IaC), Discord (notifications)
- **Inputs** : Code validé par QA, Config infra, Métriques perf, Alertes
- **Outputs** : Pipelines CI/CD, Infra provisionnée, Dashboards monitoring, Runbooks

### Agent 9 — 📝 Documentaliste (Docs Agent)

- **Rôle** : Génère et maintient toute la documentation : technique, utilisateur, API. Il assure la cohérence terminologique et la mise à jour continue à chaque changement dans le projet.
- **Pattern** : RAG + Template Engine
- **LLM** : Claude Sonnet 4.5
- **Particularités** :
  - Génère la documentation technique à partir du code source (docstrings, architecture)
  - Produit les guides utilisateur à partir des user stories et des maquettes
  - Maintient l'API Reference à partir des specs OpenAPI
  - Rédige les changelogs automatiquement à partir des PRs mergées
  - Utilise le RAG pour maintenir la cohérence terminologique (même termes partout)
  - Détecte la documentation obsolète quand le code change
  - Publie dans Notion (docs internes) et Mintlify (docs publiques)
- **Tools MCP** : GitHub (lecture du code et des PRs), Notion (publication), Filesystem
- **Inputs** : Code source, Architecture (ADRs), PRD, User Stories, Maquettes, Changelogs
- **Outputs** : Documentation technique, Guides utilisateur, API Reference, Changelogs, README

### Agent 10 — ⚖️ Avocat (Legal Agent)

- **Rôle** : Assure la conformité juridique du projet. Il vérifie les licences des dépendances, la conformité RGPD/CCPA, génère les documents juridiques (CGU, CGV, mentions légales, DPA), et alerte sur les risques légaux.
- **Pattern** : RAG + Reflection
- **LLM** : Claude Sonnet 4.5
- **Particularités** :
  - Intervient de manière **transversale** à chaque phase du projet :
    - Discovery : vérifie les contraintes réglementaires du domaine
    - Design : valide la conformité RGPD des parcours utilisateur (consentement, données personnelles)
    - Build : scanne les licences de TOUTES les dépendances (npm, pip) et alerte sur les incompatibilités (GPL vs MIT vs propriétaire)
    - Ship : génère les documents légaux (CGU, mentions légales, politique de confidentialité, DPA)
  - Utilise le RAG sur une base de connaissances juridiques (RGPD, CCPA, directives eCommerce, etc.)
  - Produit des alertes classifiées : info (recommandation), warning (risque modéré), critical (bloquant)
  - Les alertes critical bloquent la transition de phase (l'Orchestrateur ne passe pas au Ship sans validation légale)
  - ⚠️ Chaque output inclut un disclaimer : "Ceci est une analyse automatisée et ne remplace pas l'avis d'un avocat qualifié."
- **Tools MCP** : GitHub (scan des dépendances et licences), Filesystem, Notion (publication des docs légaux)
- **Inputs** : PRD, Code source (dépendances), Parcours utilisateur, Données collectées, Juridiction cible
- **Outputs** : Audit de licences, Rapport conformité RGPD, CGU/CGV/Mentions légales, DPA, Alertes juridiques

---

## Cycle de vie du projet (phases)

```
Discovery ──→ Design ──→ Build ──→ Ship ──→ Iterate
    │            │          │        │          │
 Analyste    Designer    Lead Dev  DevOps    Analyste
             Architecte  (spawn:)  Documen.  Planific.
             Planific.   Frontend  
                         Backend   
                         Mobile    
                         QA        
                         
 ────────── Avocat (transversal, toutes phases) ──────────
 ────────── Orchestrateur (routing + human gates) ────────
```

Chaque transition de phase passe par un **human gate Discord** : l'Orchestrateur poste dans #human-review et attend `approve` ou `revise`.

---

## Instructions de génération

Pour chaque agent, génère le profil complet selon le format défini dans ton system prompt :
1. Identité + LLM + Pattern d'exécution
2. System prompt opérationnel complet (sections A à I)
3. Tools MCP déclarés
4. Interface inputs/outputs avec JSON Schema
5. State contribution (reads/writes sur ProjectState)
6. Métriques d'évaluation
7. Politique d'escalade
8. Dépendances
9. Code squelette Python LangGraph

**Pour le Lead Dev (Agent 6)** : génère aussi les profils des 3 sous-agents (Frontend Web, Backend/API, Mobile) et le code du Supervisor pattern qui les spawne dynamiquement.

**Commence par l'Orchestrateur** (il définit le contrat d'interface de tout le système), puis génère les agents dans l'ordre du cycle de vie.
