# Workflow Model — Schema technique

## Structure racine

Les cles sont a la RACINE du JSON. Pas de wrapper.

| Champ | Type | Description |
|---|---|---|
| `team` | `string` | Equipe source des agents (`Shared/Teams/{team}/agents_registry.json`) |
| `phases` | `object` | Dictionnaire des phases (cle = snake_case) |
| `transitions` | `array` | Transitions entre phases |
| `parallel_groups` | `object` | Configuration des groupes paralleles |
| `rules` | `object` | Regles globales |
| `coverage_report` | `object` | Rapport de couverture agents (optionnel, genere par LLM) |
| `missing_roles` | `array` | Postes manquants identifies (optionnel, genere par LLM) |

Le champ `team` determine quelle equipe fournit les agents disponibles dans le workflow. Toutes les listes d'agents (ajout, assignation, delegation) sont construites a partir du registry de cette equipe. Le selecteur d'equipe dans l'editeur visuel met a jour ce champ.

## Phase

| Champ | Type | Requis | Description |
|---|---|---|---|
| `name` | `string` | oui | Nom affiche |
| `description` | `string` | non | Description fonctionnelle |
| `order` | `integer` | oui | Ordre sequentiel (1, 2, 3...) |
| `agents` | `object` | oui | Agents assignes a cette phase |
| `deliverables` | `object` | oui | Livrables attendus |
| `exit_conditions` | `object` | non | Conditions de sortie |
| `next_phase` | `string` | non | Override de transition (pour les boucles) |

## Agent (dans une phase)

Les agents disponibles dans le workflow proviennent du registry de l'equipe selectionnee (`Shared/Teams/{team}/agents_registry.json`). Le selecteur d'equipe dans l'editeur de workflow permet de changer l'equipe source.

| Champ | Type | Description |
|---|---|---|
| `role` | `string` | Role contextualise au projet dans cette phase |
| `required` | `boolean` | Doit terminer pour completer la phase |
| `parallel_group` | `string` | Groupe d'execution (A, B, C) |
| `depends_on` | `array[string]` | Agent IDs (MEME PHASE uniquement) dont les livrables doivent etre termines avant dispatch |
| `can_delegate_to` | `array[string]` | Agent IDs vers lesquels cet agent peut deleguer du travail |
| `delegated_by` | `string\|null` | ID de l'agent DELEGATEUR (pas de soi-meme) — si present, pas de dispatch automatique |

### depends_on (agent)

Les valeurs sont des **agent IDs simples** de la **meme phase**. Le workflow engine ne supporte PAS les references cross-phase.

```
VALIDE :   "depends_on": ["ux_designer", "architect"]
INVALIDE : "depends_on": ["discovery:architect:adrs"]       ← cross-phase interdit
INVALIDE : "depends_on": ["architect:adrs"]                  ← c'est une cle livrable, pas un agent ID
```

Le moteur resout les dependances ainsi : pour chaque agent_id dans depends_on, il verifie que TOUS les livrables required de cet agent dans la meme phase sont termines.

### Delegation

Un agent avec `delegated_by` n'est jamais dispatche automatiquement par le workflow engine. Il est dispatche par l'agent delegateur (typiquement le lead_dev qui delegue aux devs). Le `can_delegate_to` de l'agent delegateur liste les agents qu'il peut dispatcher.

`delegated_by` contient l'ID de l'agent qui DELEGUE, pas l'ID de l'agent lui-meme.

```
VALIDE :   dev_mobile a "delegated_by": "lead_dev"    ← le lead_dev delegue AU dev_mobile
INVALIDE : dev_mobile a "delegated_by": "dev_mobile"   ← auto-reference interdite
```

## Livrable (deliverable)

Chaque livrable represente une unite de travail assignee a un agent. La cle du livrable suit la convention `{agent_id}:{pipeline_step}` (renommage automatique dans l'editeur).

| Champ | Type | Requis | Description |
|---|---|---|---|
| `agent` | `string` | oui | Agent responsable |
| `pipeline_step` | `string` | oui | Cle du step dans le pipeline de l'agent |
| `required` | `boolean` | oui | Bloquant pour la phase |
| `type` | `string` | oui | Type de livrable (voir ci-dessous) |
| `description` | `string` | non | Description du livrable |
| `depends_on` | `array[string]` | non | Cles de livrables prerequis (MEME PHASE uniquement, pas de cross-phase) |
| `roles` | `array[string]` | non | Roles de l'agent actives pour ce livrable (depuis `Shared/Agents/{id}/role_*.md`) |
| `missions` | `array[string]` | non | Missions de l'agent activees pour ce livrable (depuis `Shared/Agents/{id}/mission_*.md`) |
| `skills` | `array[string]` | non | Competences de l'agent activees pour ce livrable (depuis `Shared/Agents/{id}/skill_*.md`) |

### Types de livrables

| Type | Description |
|---|---|
| `documentation` | Documents textuels (PRD, specs, audit, guides) |
| `code` | Code source (implementation, scripts) |
| `design` | Maquettes, wireframes, diagrammes UX |
| `automation` | Pipelines CI/CD, scripts d'automatisation |
| `tasklist` | Backlogs, plannings, listes de taches |
| `specs` | Specifications techniques (architecture, ADR, schemas) |
| `contract` | Documents contractuels, CGU, mentions legales |

### depends_on (livrable)

Les valeurs sont des **cles de livrables** du dictionnaire `deliverables` de la **meme phase**. Le workflow engine ne supporte PAS les references cross-phase.

```
VALIDE :   "depends_on": ["architect:adrs", "ux_designer:wireframes"]
INVALIDE : "depends_on": ["design:architect:adrs"]              ← cross-phase interdit
INVALIDE : "depends_on": ["planning:architect:architecture_spec"] ← cross-phase interdit
```

Les dependances cross-phase sont gerees implicitement par les groupes paralleles et les transitions. Il n'est pas necessaire de les declarer.

### Cle de sortie

La cle de sortie dans le state est `{agent_id}:{pipeline_step}`. Elle doit etre unique par agent dans tout le workflow. Si deux livrables du meme agent ont le meme pipeline_step, le second ecrase le premier.

### Profil livrable (roles, missions, skills)

Chaque livrable peut specifier quels roles, missions et competences de l'agent sont actives pour cette tache. Ces valeurs correspondent aux fichiers `role_*.md`, `mission_*.md` et `skill_*.md` dans le catalogue agent (`Shared/Agents/{id}/`).

L'editeur de workflow propose une baguette magique (skill-match) qui appelle un LLM pour auto-selectionner les roles/missions/skills pertinents en fonction de la description du livrable et du profil de l'agent.

## Transition

`transitions` est un **ARRAY d'objets**, PAS un dictionnaire.

| Champ | Type | Description |
|---|---|---|
| `from` | `string` | Phase source |
| `to` | `string` | Phase destination |
| `human_gate` | `boolean` | Validation humaine requise avant transition |
| `from_side` | `string` | Cote de sortie sur le canvas (left, right, top, bottom) |
| `to_side` | `string` | Cote d'arrivee sur le canvas (left, right, top, bottom) |

```
VALIDE :   "transitions": [{"from": "discovery", "to": "design", "human_gate": true, "from_side": "right", "to_side": "left"}]
INVALIDE : "transitions": {"discovery": ["design"]}   ← le moteur attend un ARRAY d'objets avec from/to
```

Les champs `from_side` et `to_side` sont utilises par l'editeur visuel pour le positionnement des fleches.

## Groupes paralleles

```json
{
  "description": "Les agents du meme groupe tournent en parallele. B attend A. C attend B.",
  "order": ["A", "B", "C"]
}
```

- Groupe A dispatche en premier
- Groupe B attend que tous les livrables required du groupe A soient termines
- Groupe C attend que tous les livrables required du groupe B soient termines
- Auto-dispatch recursif (max 5 niveaux) : quand un groupe termine, le gateway verifie s'il y a un groupe suivant et le dispatche automatiquement

## Regles globales

| Champ | Type | Description |
|---|---|---|
| `critical_alert_blocks_transition` | `boolean` | Bloque la transition si alertes critiques |
| `human_gate_required_for_all_transitions` | `boolean` | Force validation humaine sur toutes les transitions |
| `lead_dev_only_dispatcher_for_devs` | `boolean` | Seul le lead dev peut dispatcher les devs |
| `qa_must_run_after_dev` | `boolean` | Le QA ne demarre qu'apres les devs |
| `max_agents_parallel` | `integer` | Nombre maximum d'agents simultanes |

## Conditions de sortie

| Condition | Description |
|---|---|
| `all_deliverables_complete` | Tous les livrables required sont termines |
| `no_critical_alerts` | Aucune alerte critique en cours |
| `qa_verdict_go` | Le QA a donne un verdict positif |
| `staging_validated` | L'environnement de staging est valide |
| `human_gate` | Validation humaine requise |
| `no_critical_bugs` | Aucun bug critique ouvert |

## Statuts livrable

```
(absent) → pending → complete → pending_review → approved
```

Les statuts `complete`, `pending_review` et `approved` sont consideres comme termines pour la resolution des dependances.

## Dispatch

Pour chaque groupe parallele dans l'ordre :

1. Verifier que tous les livrables required des groupes precedents sont termines
2. Pour chaque livrable du groupe courant :
   - Verifier que ses `depends_on` sont satisfaits
   - Si oui, dispatcher l'agent avec le `pipeline_step` du livrable
3. Un seul groupe actif a la fois
4. Quand le groupe courant termine, auto-dispatch du groupe suivant (recursif, max 5 niveaux)
5. Quand tous les groupes sont termines, verifier les exit conditions de la phase

### Fallback disque

En cas de perte de state (redemarrage), le workflow engine peut verifier l'existence de fichiers livrables sur le disque (`/root/ag.flow/projects/{slug}/{team_id}/{workflow}/`) et marquer les livrables correspondants comme `complete`.

## Fichiers associes

### Workflow

| Fichier | Emplacement | Description |
|---|---|---|
| `Workflow.json` | `Shared/Teams/{team}/` | Workflow template d'equipe |
| `{name}.wrk.json` | `Shared/Projects/{project}/` | Workflow de projet |
| `{name}.wrk.design.json` | `Shared/Projects/{project}/` | Positions des phases sur le canvas (fichier design) |
| `workflows_design.json` | `Shared/Teams/{team}/` | Positions des phases pour le workflow template |

### Agents

| Fichier | Emplacement | Description |
|---|---|---|
| `agents_registry.json` | `Shared/Teams/{team}/` | Liste des agents de l'equipe avec type, pipeline_steps |
| `agent.json` | `Shared/Agents/{id}/` | Config agent (nom, type, capabilities, delivers_*) |
| `identity.md` | `Shared/Agents/{id}/` | Identite de l'agent |
| `role_*.md` | `Shared/Agents/{id}/` | Fichiers de roles (un par role) |
| `mission_*.md` | `Shared/Agents/{id}/` | Fichiers de missions (un par mission) |
| `skill_*.md` | `Shared/Agents/{id}/` | Fichiers de competences (un par competence) |

## Editeur visuel

L'editeur de workflow dans le dashboard admin offre :

- **Canvas visuel** avec phases draggables et fleches de transition (courbes de Bezier)
- **Selecteur d'equipe** dans les proprietes du workflow — charge les agents depuis le registry de l'equipe selectionnee
- **Ajout d'agents** par dropdown — liste filtree depuis le registry de l'equipe
- **Groupes paralleles** editables (A → Z)
- **Baguette magique** (skill-match) pour auto-selectionner roles/missions/skills d'un livrable
- **Vue JSON** pour edition directe du workflow
- **Double fichier** : le workflow (`.wrk.json`) et le design (`.wrk.design.json`) sont sauvegardes separement
