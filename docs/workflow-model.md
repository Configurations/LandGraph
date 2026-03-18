# Workflow Model — Schema technique

## Structure racine

Les cles sont a la RACINE du JSON. Pas de wrapper.

| Champ | Type | Description |
|---|---|---|
| `phases` | `object` | Dictionnaire des phases (cle = snake_case) |
| `transitions` | `array` | Transitions entre phases |
| `parallel_groups` | `object` | Configuration des groupes paralleles |
| `rules` | `object` | Regles globales |
| `coverage_report` | `object` | Rapport de couverture agents (optionnel) |
| `missing_roles` | `array` | Postes manquants identifies (optionnel) |

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

| Champ | Type | Description |
|---|---|---|
| `role` | `string` | Role contextualise au projet dans cette phase |
| `required` | `boolean` | Doit terminer pour completer la phase |
| `parallel_group` | `string` | Groupe d'execution (A, B, C) |
| `depends_on` | `array[string]` | Agent IDs dont les livrables doivent etre termines |
| `can_delegate_to` | `array[string]` | Agent IDs delegables |
| `delegated_by` | `string` | Agent delegateur (pas de dispatch automatique) |

## Livrable (deliverable)

| Champ | Type | Description |
|---|---|---|
| `agent` | `string` | Agent responsable |
| `required` | `boolean` | Bloquant pour la phase |
| `type` | `string` | documentation, code, design, automation, tasklist, specs |
| `description` | `string` | Description du livrable |
| `pipeline_step` | `string` | Cle unique par agent (defaut = cle du livrable) |
| `depends_on` | `array[string]` | Cles de livrables prerequis (meme phase) |

Cle de sortie dans le state : `{agent_id}:{pipeline_step}` — doit etre unique par agent dans tout le workflow.

## Transition

| Champ | Type | Description |
|---|---|---|
| `from` | `string` | Phase source |
| `to` | `string` | Phase destination |
| `human_gate` | `boolean` | Validation humaine requise |

## Groupes paralleles

`order: ["A", "B", "C"]` — groupe A dispatche en premier, B attend que A termine, C attend B. Auto-dispatch recursif (max 5 niveaux).

## Regles globales

| Champ | Type | Description |
|---|---|---|
| `critical_alert_blocks_transition` | `boolean` | Bloque si alertes critiques |
| `human_gate_required_for_all_transitions` | `boolean` | Force validation humaine |
| `lead_dev_only_dispatcher_for_devs` | `boolean` | Lead dev seul dispatcher |
| `qa_must_run_after_dev` | `boolean` | QA apres les devs |
| `max_agents_parallel` | `integer` | Max agents simultanes |

## Conditions de sortie

all_deliverables_complete, no_critical_alerts, qa_verdict_go, staging_validated, human_gate, no_critical_bugs.

## Statuts livrable

(absent) → pending → complete → pending_review → approved. Les statuts complete/pending_review/approved sont consideres termines pour les dependances.

## Dispatch

Pour chaque groupe parallele dans l'ordre : verifier que les livrables requis des groupes precedents sont termines, puis dispatcher les livrables du groupe dont les depends_on sont satisfaits. Un seul groupe a la fois.
