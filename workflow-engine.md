# Workflow Engine — workflow_engine.py

Lit `Workflow.json` depuis le dossier de l'équipe et pilote le cycle de vie du projet.

## Fonctions principales

| Fonction | Rôle |
|---|---|
| `get_deliverables_to_dispatch(phase, outputs, team)` | Quels livrables lancer maintenant ? (par parallel_group + depends_on) |
| `get_agents_to_dispatch(phase, outputs, team)` | Legacy : quels agents lancer (utilisé par orchestrateur Discord) |
| `check_phase_complete(phase, outputs, team)` | La phase est-elle terminée ? (clé `agent_id:pipeline_step`) |
| `can_transition(phase, outputs, alerts, team)` | Peut-on passer à la phase suivante ? |
| `get_workflow_status(phase, outputs, team)` | État complet pour l'affichage |

## Parallel Groups

Les agents d'une phase sont organisés en groupes ordonnés (A, B, C). Le groupe B ne démarre qu'après que le groupe A soit complet.

```
Discovery : A = [requirements_analyst, legal_advisor]
Design :    A = [ux_designer, architect, planner]
Build :     A = [lead_dev] → B = [dev_frontend, dev_backend, dev_mobile] → C = [qa_engineer]
```

## Catégories de livrables

Arborescence 2 niveaux dans Workflow.json (`categories` à la racine). Chaque livrable a un champ optionnel `"category"` : `"parentId/childId"` (sous-catégorie) ou `"parentId"` (racine). Absent ou `""` = non catégorisé.

## Dispatch par livrables

Chaque livrable dans `Workflow.json` a un `agent` + `pipeline_step`. Le dispatch se fait livrable par livrable :

```
Phase transition (HITL approve)
  → get_deliverables_to_dispatch(phase, outputs, team)
  → Pour chaque livrable : agent reçoit prompt + assign + unassign + mission (instruction du step)
  → agent_outputs["requirements_analyst:prd"] = {status: "complete", deliverables: {...}}
```

Les livrables héritent du `parallel_group` de leur agent. Groupe A termine → groupe B démarre. Max 5 niveaux.

## Auto-dispatch dans le gateway

Après qu'un groupe de livrables termine, le gateway redemande au workflow engine s'il y a un groupe suivant. Chaînage automatique récursif (max 5 niveaux).

```
Livrables groupe A terminent → workflow engine : "groupe B suivant" → auto-dispatch B
Livrables groupe B terminent → workflow engine : "groupe C suivant" → auto-dispatch C
Groupe C termine → workflow engine : "phase complete" → propose human_gate
```
