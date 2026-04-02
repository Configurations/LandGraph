# Leçons apprises

<!-- Claude ajoute ici les erreurs corrigées et bonnes pratiques découvertes -->
<!-- Format : - [module concerné] description courte -->
<!-- Max 50 lignes — consolider les leçons similaires si nécessaire -->

- [orchestrator] Ne jamais faire produire du JSON structuré au LLM en texte libre — utiliser le tool use natif (bind_tools). Le parsing JSON est fragile (marqueurs markdown imbriqués, texte ajouté autour).
- [orchestrator] Les MCP tools sont async-only (StructuredTool) — utiliser ainvoke avec fallback ThreadPoolExecutor, pas invoke directement.
- [orchestrator_tools] Ne jamais hardcoder l'agent_id — le lire depuis teams.json via get_team_info(). La casse des IDs varie selon le registry.
- [prompts] Ne jamais mettre de prompts ni de messages utilisateur dans le code Python — les externaliser dans Models/{culture}/ ou messages.json (i18n).
- [prompts] Les marqueurs de questions doivent éviter les conflits markdown — (((? ... ))) au lieu de ```? ... ``` (le LLM met du JSON dans des blocs ``` qui cassent le parsing).
- [prompts] Les LLM ne comptent pas — injecter le compteur de questions dans le message user si on veut limiter le nombre d'échanges.
- [prompts] Les instructions de format (reformuler, valider, indexer) doivent être impératives et positionnées en premier — sinon le LLM les ignore pour optimiser.
- [gateway] load_or_create_state : ne pas conditionner le chargement du state existant sur agent_outputs — un thread onboarding n'a pas d'outputs mais a un historique.
- [analysis_service] Le status DB dispatcher_tasks a une contrainte CHECK — utiliser 'waiting_hitl' pas 'waiting_input'.
- [analysis_service] Ne pas stocker les réponses utilisateur en doublon (hitl_requests + rag_conversations) — skip_store=True quand c'est une réponse à une question HITL.
- [pg_notify] Le trigger hitl_response doit inclure team_id dans le payload — sinon le WS listener ignore l'event (check team_id vide → return).
- [deploy] Le Dockerfile.hitl fait un build frontend dans le container (multi-stage) — les fichiers hitl/static/ locaux sont ignorés. Il faut deploy.sh pour sync hitl-frontend/ puis rebuild.
- [deploy] Shared/ et config/ ne sont jamais écrasés par deploy.sh — les fichiers Models doivent être copiés manuellement (SCP) ou via le dashboard admin.
- [frontend] Les questions fermées doivent être multi-select par défaut — les utilisateurs veulent souvent cocher plusieurs options.
- [frontend] Le composant InteractiveQuestions est partagé entre AnalysisChatMessage et AnswerModal — tout changement UI s'applique aux deux.
