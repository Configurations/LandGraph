"""BaseAgent — Pipeline + ReAct MCP tools + Discord streaming."""
import json, logging, os
from datetime import datetime, timezone
from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from agents.shared.event_bus import bus, Event

load_dotenv()
logger = logging.getLogger(__name__)
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")


def _post_to_discord_sync(channel_id, message):
    if not DISCORD_BOT_TOKEN or not channel_id:
        return
    import requests
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}", "Content-Type": "application/json"}

    for chunk in _smart_split(message, 1900):
        try:
            requests.post(url, headers=headers, json={"content": chunk}, timeout=10)
        except Exception as e:
            logger.error(f"Discord: {e}")


def _smart_split(text, max_len=1900):
    """Decoupe un message en chunks Discord en coupant sur les sauts de ligne."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""

    for line in text.split("\n"):
        # Si une seule ligne depasse max_len, la couper par mots
        if len(line) > max_len:
            if current:
                chunks.append(current.rstrip())
                current = ""
            words = line.split(" ")
            for word in words:
                if len(current) + len(word) + 1 > max_len:
                    if current:
                        chunks.append(current.rstrip())
                    current = word + " "
                else:
                    current += word + " "
            continue

        # Ajouter la ligne au chunk courant
        if len(current) + len(line) + 1 > max_len:
            chunks.append(current.rstrip())
            current = line + "\n"
        else:
            current += line + "\n"

    if current.strip():
        chunks.append(current.rstrip())

    return chunks


def _format_deliverable(key, val, depth=0):
    """Formate un livrable pour Discord — lisible, structure, pas trop long."""
    indent = "  " * depth
    max_len = 1500 if depth == 0 else 500

    if val is None:
        return f"{indent}_(vide)_"

    if isinstance(val, bool):
        return f"{indent}{'✅' if val else '❌'}"

    if isinstance(val, (int, float)):
        return f"{indent}{val}"

    if isinstance(val, str):
        val = val.strip()
        if len(val) > max_len:
            return f"{indent}{val[:max_len]}..."
        return f"{indent}{val}"

    if isinstance(val, dict):
        if not val:
            return f"{indent}_(vide)_"
        parts = []
        for k, v in list(val.items())[:8]:
            label = k.replace("_", " ").title()
            if isinstance(v, bool):
                parts.append(f"{indent}{'✅' if v else '❌'} {label}")
            elif isinstance(v, (str, int, float)) and not isinstance(v, bool):
                sv = str(v)
                if len(sv) > 200:
                    sv = sv[:200] + "..."
                parts.append(f"{indent}▸ **{label}** : {sv}")
            elif isinstance(v, list):
                if len(v) == 0:
                    parts.append(f"{indent}▸ **{label}** : _(vide)_")
                elif all(isinstance(i, str) for i in v):
                    items = ", ".join(v[:10])
                    if len(v) > 10:
                        items += f" ... (+{len(v)-10})"
                    parts.append(f"{indent}▸ **{label}** : {items}")
                else:
                    parts.append(f"{indent}▸ **{label}** ({len(v)} elements)")
                    if depth < 2:
                        for item in v[:3]:
                            parts.append(_format_deliverable("", item, depth + 1))
                        if len(v) > 3:
                            parts.append(f"{indent}  _... et {len(v)-3} de plus_")
            elif isinstance(v, dict):
                if depth < 2:
                    parts.append(f"{indent}▸ **{label}** :")
                    parts.append(_format_deliverable("", v, depth + 1))
                else:
                    parts.append(f"{indent}▸ **{label}** : {len(v)} champs")
            else:
                parts.append(f"{indent}▸ **{label}** : {str(v)[:150]}")
        if len(val) > 8:
            parts.append(f"{indent}_... et {len(val)-8} champs de plus_")
        return "\n".join(parts)

    if isinstance(val, list):
        if not val:
            return f"{indent}_(vide)_"
        parts = []
        for item in val[:5]:
            if isinstance(item, dict):
                # Ligne compacte pour les dicts dans une liste
                summary = " | ".join(
                    f"**{k.replace('_',' ').title()}**: {str(v)[:60]}"
                    for k, v in list(item.items())[:4]
                )
                parts.append(f"{indent}• {summary}")
            elif isinstance(item, str):
                parts.append(f"{indent}• {item[:200]}")
            else:
                parts.append(f"{indent}• {str(item)[:200]}")
        if len(val) > 5:
            parts.append(f"{indent}_... et {len(val)-5} de plus_")
        return "\n".join(parts)

    return f"{indent}{str(val)[:300]}"


def _format_output_for_discord(agent_name, deliverables):
    """Formate tous les livrables d'un agent pour Discord."""
    if not deliverables:
        return f"✅ **{agent_name}** termine\n_(pas de livrables)_"

    msg = f"✅ **{agent_name}** termine\n"

    if isinstance(deliverables, dict):
        skip = {"agent_id", "status", "confidence", "timestamp", "parse_note"}
        items = {k: v for k, v in deliverables.items() if k not in skip}
        if not items:
            items = deliverables

        # Grouper les booleens et nombres sur une ligne
        checks = []
        details = {}
        for k, v in items.items():
            if isinstance(v, bool):
                emoji = "✅" if v else "❌"
                checks.append(f"{emoji} {k.replace('_', ' ').title()}")
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                checks.append(f"**{k.replace('_', ' ').title()}**: {v}")
            else:
                details[k] = v

        if checks:
            msg += "\n" + " · ".join(checks) + "\n"

        for k in list(details.keys())[:5]:
            label = k.replace("_", " ").title()
            formatted = _format_deliverable(k, details[k])
            if len(formatted) > 5:
                msg += f"\n📎 **{label}**\n{formatted}\n"

    elif isinstance(deliverables, str):
        msg += f"\n{deliverables[:1500]}\n"

    return msg


class BaseAgent:
    agent_id = "base"
    agent_name = "Base Agent"
    default_model = "claude-sonnet-4-5-20250929"
    default_llm = ""  # nom du provider dans llm_providers.json
    default_temperature = 0.3
    default_max_tokens = 32768
    prompt_filename = "base.md"
    steps = []
    use_tools = False
    requires_approval = False

    def __init__(self):
        # Le provider peut etre defini via : env var > registry (default_llm) > default
        self.llm_provider = os.getenv(f"{self.agent_id.upper()}_LLM", self.default_llm) or None
        self.temperature = float(os.getenv(f"{self.agent_id.upper()}_TEMPERATURE", str(self.default_temperature)))
        self.max_tokens = int(os.getenv(f"{self.agent_id.upper()}_MAX_TOKENS", str(self.default_max_tokens)))
        # Resolve model name: env override > provider config > class default
        explicit_model = os.getenv(f"{self.agent_id.upper()}_MODEL")
        if explicit_model:
            self.model = explicit_model
        else:
            from agents.shared.llm_provider import get_default_provider, get_provider_config
            prov = self.llm_provider or get_default_provider()
            self.model = get_provider_config(prov).get("model", self.default_model)
            if not self.llm_provider:
                self.llm_provider = prov
        self.system_prompt = self._load_prompt()
        self._tools = None

    def _load_prompt(self):
        from agents.shared.team_resolver import find_team_file
        team_id = getattr(self, 'team_id', 'default')

        # 1. Chercher dans le dossier de l'equipe (config/Teams/<team>/<prompt>.md)
        path = find_team_file(team_id, self.prompt_filename)
        if path:
            logger.info(f"[{self.agent_id}] Prompt: {path}")
            return open(path).read()

        # 2. Fallback vers Shared/Agents/<agent_id>/prompt.md (mounted as /app/shared_agents)
        for base in ['/app/shared_agents', '/app/Shared/Agents', 'Shared/Agents']:
            shared_path = os.path.join(base, self.agent_id, 'prompt.md')
            if os.path.exists(shared_path):
                logger.info(f"[{self.agent_id}] Prompt (shared): {shared_path}")
                return open(shared_path).read()

        # Fallback minimal — prompt will be overridden at runtime (onboarding, deliverable dispatch)
        logger.debug(f"[{self.agent_id}] No prompt file found — using fallback (will be overridden at runtime)")
        return f"Tu es {self.agent_name}. JSON: {{agent_id, status, confidence, deliverables}}"

    def get_llm(self):
        from agents.shared.llm_provider import create_llm
        return create_llm(
            provider_name=self.llm_provider,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def get_tools(self):
        if self._tools is None and self.use_tools:
            try:
                from agents.shared.mcp_client import get_tools_for_agent
                team_id = getattr(self, 'team_id', None)
                self._tools = get_tools_for_agent(self.agent_id, team_id)
                if self._tools:
                    logger.info(f"[{self.agent_id}] {len(self._tools)} MCP tools loaded")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] MCP tools failed: {e}")
                self._tools = []

            # Ajouter le tool ask_human pour la boucle conversationnelle
            try:
                self._tools = list(self._tools or [])
                self._tools.append(self._create_ask_human_tool())
                logger.info(f"[{self.agent_id}] ask_human tool added")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] ask_human tool failed: {e}")

        return self._tools or []

    def _create_ask_human_tool(self):
        """Cree un tool LangChain pour poser des questions aux humains."""
        from langchain_core.tools import tool
        agent_ref = self

        @tool
        def ask_human(question: str, context: str = "") -> str:
            """Pose une question a l'humain et attend sa reponse.
            Utilise ce tool quand tu as besoin d'une clarification, d'un choix,
            ou d'une information que seul l'humain peut fournir.
            Args:
                question: La question a poser
                context: Contexte optionnel pour aider l'humain a repondre
            Returns:
                La reponse de l'humain ou un message de timeout
            """
            current_state = getattr(agent_ref, '_current_state', {})
            thread_id = current_state.get("_thread_id", "")
            team_id = current_state.get("_team_id", "default")

            # Onboarding mode: write to hitl_requests in DB for HITL console
            if thread_id.startswith("onboarding-"):
                import psycopg
                db_uri = os.getenv("DATABASE_URI", "")
                if db_uri:
                    try:
                        with psycopg.connect(db_uri, autocommit=True) as conn:
                            with conn.cursor() as cur:
                                cur.execute(
                                    """INSERT INTO project.hitl_requests
                                       (thread_id, agent_id, team_id, request_type, prompt, context, channel, status)
                                       VALUES (%s, %s, %s, 'question', %s, %s::jsonb, 'hitl-console', 'pending')
                                       RETURNING id""",
                                    (thread_id, agent_ref.agent_id, team_id, question, json.dumps({"context": context}) if context else "{}"),
                                )
                                row = cur.fetchone()
                                request_id = str(row[0]) if row else ""
                        logger.info(f"[{agent_ref.agent_id}] ask_human via HITL: {request_id}")
                        return f"Question posee a l'utilisateur (request {request_id}). En attente de reponse."
                    except Exception as e:
                        logger.error(f"[{agent_ref.agent_id}] ask_human HITL error: {e}")

            # Default: use Discord/Email channel
            from agents.shared.agent_conversation import ask_human_sync
            channel_id = os.getenv("DISCORD_CHANNEL_COMMANDS", "")
            result = ask_human_sync(
                agent_ref.agent_name, question, channel_id, context, timeout=1800,
                thread_id=thread_id, team_id=team_id,
            )
            if result["answered"]:
                return f"Reponse de {result['author']}: {result['response']}"
            elif result["timed_out"]:
                return "Pas de reponse (timeout 5 min). Continue avec ton meilleur jugement."
            else:
                return "Erreur de communication. Continue avec ton meilleur jugement."

        return ask_human

    def _extract_brief(self, state):
        m = state.get("project_metadata", {})
        if isinstance(m, dict) and m.get("brief"):
            return m["brief"]
        for msg in state.get("messages", []):
            if isinstance(msg, tuple) and len(msg) == 2 and msg[0] == "user" and len(msg[1]) > 20:
                return msg[1]
            elif hasattr(msg, "content"):
                c = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(c) > 20:
                    return c
        return "Aucun brief."

    def _extract_task(self, state):
        for d in reversed(state.get("decision_history", [])):
            for a in d.get("actions", []):
                if isinstance(a, dict) and a.get("target") == self.agent_id:
                    return a.get("task") or ""
                elif hasattr(a, "target") and a.target == self.agent_id:
                    return a.task or ""
        return ""

    def _get_channel_id(self, state):
        return state.get("_discord_channel_id", "") or os.getenv("DISCORD_CHANNEL_COMMANDS", "")

    def build_context(self, state):
        o = state.get("agent_outputs", {})
        # Ne garder que les outputs reussis dans le contexte
        successful = {k: v for k, v in o.items() if isinstance(v, dict) and v.get("status") == "complete"}
        ctx = {
            "project_phase": state.get("project_phase", "unknown"),
            "project_metadata": state.get("project_metadata", {}),
            "brief": self._extract_brief(state),
            "task": self._extract_task(state),
            "existing_outputs": list(successful.keys()),
            "relevant_outputs": {
                k: {"status": v.get("status"), "keys": list(v.get("deliverables", {}).keys())}
                for k, v in successful.items()
            },
        }
        # Inject previous phase syntheses from filesystem
        slug = state.get("project_slug", "")
        if slug:
            try:
                from agents.shared.project_store import get_previous_syntheses, read_project_docs
                phase = state.get("project_phase", "discovery")
                syntheses = get_previous_syntheses(slug, phase)
                if syntheses:
                    ctx["previous_phases"] = syntheses
                # For discovery phase, inject user-provided docs
                if phase == "discovery":
                    docs = read_project_docs(slug)
                    if docs:
                        ctx["project_documents"] = docs[:20000]
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Project context injection error: {e}")
        return ctx

    def parse_response(self, raw):
        c = raw.strip()
        # Extract from code blocks
        if "```json" in c:
            c = c.split("```json")[1].split("```")[0].strip()
        elif "```" in c:
            c = c.split("```")[1].split("```")[0].strip()
        # Try direct parse
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            pass
        # Fallback: find first { or [ and parse from there
        for ch in ['{', '[']:
            idx = c.find(ch)
            if idx >= 0:
                try:
                    return json.loads(c[idx:])
                except json.JSONDecodeError:
                    pass
        # Fallback: try from raw (skip any preamble text before JSON)
        for ch in ['{', '[']:
            idx = raw.find(ch)
            if idx >= 0:
                try:
                    return json.loads(raw[idx:])
                except json.JSONDecodeError:
                    # Try trimming trailing text after last } or ]
                    closing = '}' if ch == '{' else ']'
                    ridx = raw.rfind(closing)
                    if ridx > idx:
                        try:
                            return json.loads(raw[idx:ridx + 1])
                        except json.JSONDecodeError:
                            pass
        # Nothing worked
        logger.error(f"[parse_response] FAIL raw={len(raw)}c, starts={repr(raw[:80])}, has_backtick={'```' in raw}")
        raise json.JSONDecodeError("No valid JSON found in response", raw[:200], 0)

    # ── Appels LLM ───────────────────────────────────────────────────────────

    def _get_callbacks(self):
        """Get Langfuse callbacks with session_id from current state."""
        from agents.shared.langfuse_setup import get_langfuse_callbacks
        state = getattr(self, "_current_state", None) or {}
        thread_id = state.get("_thread_id", "") or ""
        # Try configurable thread_id from LangGraph
        if not thread_id and isinstance(state, dict):
            for m in state.get("messages", []):
                break  # just need the state reference
        return get_langfuse_callbacks(session_id=thread_id, trace_name=self.agent_id)

    def _call_llm(self, instruction, context, previous_results=None, _state=None):
        from agents.shared.rate_limiter import throttled_invoke
        llm = self.get_llm()
        uc = f"Contexte:\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        if previous_results:
            ps = json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)
            if len(ps) > 15000:
                ps = ps[:15000] + "\n...(tronque)"
            uc += f"Precedents:\n```json\n{ps}\n```\n\n"
        lang = context.get("project_metadata", {}).get("language", "fr")
        lang_label = {"fr": "français", "en": "English", "es": "español", "de": "Deutsch"}.get(lang, lang)
        uc += f"Instruction: {instruction}\n\nIMPORTANT: Reponds UNIQUEMENT avec du JSON valide (commencant par {{ et finissant par }}). Pas de texte explicatif, pas de code block markdown. Redige tout le contenu en {lang_label}."
        msgs = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": uc},
        ]
        st = _state or {}
        bus.emit(Event("llm_call_start", agent_id=self.agent_id,
                        thread_id=st.get("_thread_id", ""), team_id=st.get("_team_id", ""),
                        data={"provider": self.llm_provider, "model": self.model, "messages_count": len(msgs)}))
        r = throttled_invoke(llm, msgs, provider_name=self.llm_provider, model=self.model, callbacks=self._get_callbacks())
        raw = r.content if isinstance(r.content, str) else str(r.content)
        tokens = {}
        if hasattr(r, "usage_metadata") and r.usage_metadata:
            tokens = {"input_tokens": getattr(r.usage_metadata, "input_tokens", 0),
                      "output_tokens": getattr(r.usage_metadata, "output_tokens", 0),
                      "total_tokens": getattr(r.usage_metadata, "total_tokens", 0)}
        bus.emit(Event("llm_call_end", agent_id=self.agent_id,
                        thread_id=st.get("_thread_id", ""), team_id=st.get("_team_id", ""),
                        data={"provider": self.llm_provider, "model": self.model,
                              "output_chars": len(raw), **tokens}))
        logger.info(f"[{self.agent_id}] LLM: {len(raw)}c")
        return raw

    def _call_llm_with_tools(self, instruction, context, previous_results=None, _state=None):
        from agents.shared.rate_limiter import throttled_invoke
        tools = self.get_tools()
        if not tools:
            return self._call_llm(instruction, context, previous_results, _state=_state)

        llm = self.get_llm()
        llm_t = llm.bind_tools(tools)
        st = _state or {}

        uc = f"Contexte:\n```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        if previous_results:
            ps = json.dumps(previous_results, indent=2, default=str, ensure_ascii=False)
            if len(ps) > 15000:
                ps = ps[:15000] + "\n...(tronque)"
            uc += f"Precedents:\n```json\n{ps}\n```\n\n"
        lang = context.get("project_metadata", {}).get("language", "fr")
        lang_label = {"fr": "français", "en": "English", "es": "español", "de": "Deutsch"}.get(lang, lang)
        uc += f"Instruction: {instruction}\n\nRedige tout le contenu en {lang_label}."

        msgs = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": uc},
        ]

        max_iters = 3
        for iteration in range(max_iters):
            # Last iteration: strip tools and force JSON output
            use_llm = llm_t
            if iteration == max_iters - 1:
                use_llm = llm  # raw LLM without tools
                logger.info(f"[{self.agent_id}] ReAct: last iter, stripping tools, forcing JSON")
                msgs.append({"role": "user", "content": "STOP les appels d'outils. Produis maintenant le JSON final avec toutes les informations que tu as collectees. Reponds UNIQUEMENT avec le JSON brut commencant par { et finissant par }."})

            bus.emit(Event("llm_call_start", agent_id=self.agent_id,
                            thread_id=st.get("_thread_id", ""), team_id=st.get("_team_id", ""),
                            data={"provider": self.llm_provider, "model": self.model,
                                  "messages_count": len(msgs), "iteration": iteration + 1}))
            from agents.shared.langfuse_setup import get_langfuse_callbacks
            resp = throttled_invoke(use_llm, msgs, provider_name=self.llm_provider, model=self.model, callbacks=self._get_callbacks())
            tokens = {}
            if hasattr(resp, "usage_metadata") and resp.usage_metadata:
                tokens = {"input_tokens": getattr(resp.usage_metadata, "input_tokens", 0),
                          "output_tokens": getattr(resp.usage_metadata, "output_tokens", 0),
                          "total_tokens": getattr(resp.usage_metadata, "total_tokens", 0)}
            bus.emit(Event("llm_call_end", agent_id=self.agent_id,
                            thread_id=st.get("_thread_id", ""), team_id=st.get("_team_id", ""),
                            data={"provider": self.llm_provider, "model": self.model,
                                  "output_chars": len(resp.content) if isinstance(resp.content, str) else 0,
                                  "has_tool_calls": bool(resp.tool_calls), **tokens}))
            msgs.append(resp)

            if not resp.tool_calls:
                raw = resp.content if isinstance(resp.content, str) else str(resp.content)
                # If response is empty or not JSON-like, retry up to 2 times
                # But accept rich text responses (>200 chars) — they contain useful content
                needs_retry = False
                if not raw.strip():
                    needs_retry = True
                elif len(raw.strip()) < 200 and not raw.strip().startswith('{') and not raw.strip().startswith('[') and '```json' not in raw:
                    needs_retry = True
                if needs_retry and iteration < max_iters - 1:
                    retry_count = sum(1 for m in msgs if isinstance(m, dict) and m.get("role") == "user" and "JSON" in m.get("content", ""))
                    if retry_count < 1:
                        logger.info(f"[{self.agent_id}] ReAct response empty/not JSON, requesting structured output (retry {retry_count+1})")
                        msgs.append({"role": "user", "content": "Ta reponse est vide ou n'est pas du JSON. Reponds UNIQUEMENT avec le JSON structure demande. Pas de texte explicatif, pas de code block markdown, juste le JSON brut commencant par { et finissant par }."})
                        continue
                logger.info(f"[{self.agent_id}] ReAct done — {iteration + 1} iters, raw={len(raw)}c, starts={repr(raw[:30])}")
                return raw

            for tc in resp.tool_calls:
                tn, ta = tc["name"], tc["args"]
                logger.info(f"[{self.agent_id}] Tool: {tn}({json.dumps(ta, default=str)[:200]})")

                result = "Tool not found"
                for t in tools:
                    if t.name == tn:
                        try:
                            if hasattr(t, "ainvoke"):
                                import asyncio
                                try:
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        import concurrent.futures
                                        with concurrent.futures.ThreadPoolExecutor() as pool:
                                            result = pool.submit(asyncio.run, t.ainvoke(ta)).result()
                                    else:
                                        result = asyncio.run(t.ainvoke(ta))
                                except RuntimeError:
                                    result = asyncio.run(t.ainvoke(ta))
                            else:
                                result = t.invoke(ta)
                            if isinstance(result, (dict, list)):
                                result = json.dumps(result, ensure_ascii=False, default=str)
                            result = str(result)[:5000]
                        except Exception as e:
                            result = f"Tool error: {e}"
                            logger.error(f"[{self.agent_id}] Tool {tn}: {e}")
                        break

                bus.emit(Event("tool_call", agent_id=self.agent_id,
                                thread_id=st.get("_thread_id", ""), team_id=st.get("_team_id", ""),
                                data={"tool_name": tn, "args": json.dumps(ta, default=str)[:300],
                                      "result_length": len(result)}))
                msgs.append(ToolMessage(content=result, tool_call_id=tc["id"]))

        # Max iterations reached — do one final call without tools to force JSON output
        logger.warning(f"[{self.agent_id}] ReAct max iters — final JSON extraction call")
        msgs.append({"role": "user", "content": "Tu as atteint la limite d'iterations. Produis MAINTENANT le JSON final avec toutes les informations collectees. JSON brut uniquement, commencant par { et finissant par }."})
        try:
            from agents.shared.langfuse_setup import get_langfuse_callbacks
            final_resp = throttled_invoke(llm, msgs, provider_name=self.llm_provider, model=self.model, callbacks=self._get_callbacks())
            raw = final_resp.content if isinstance(final_resp.content, str) else str(final_resp.content)
            if raw.strip():
                logger.info(f"[{self.agent_id}] Final extraction: {len(raw)}c")
                return raw
        except Exception as e:
            logger.error(f"[{self.agent_id}] Final extraction failed: {e}")
        last = msgs[-2] if len(msgs) > 1 else msgs[-1]
        return last.content if hasattr(last, "content") and isinstance(last.content, str) else str(last)

    # ── Modes d'execution ────────────────────────────────────────────────────

    def _run_steps(self, state):
        ctx = self.build_context(state)
        ch = self._get_channel_id(state)
        dl = {}

        for i, step in enumerate(self.steps, 1):
            sn, ins, ok = step["name"], step["instruction"], step["output_key"]
            logger.info(f"[{self.agent_id}] Step {i}/{len(self.steps)}: {sn}")
            self._evt("step_start", state, step=i, total=len(self.steps), step_name=sn)
            _post_to_discord_sync(ch, f"⏳ **{self.agent_name}** — etape {i}/{len(self.steps)} : **{sn}**...")

            if self.use_tools:
                raw = self._call_llm_with_tools(ins, ctx, dl if dl else None, _state=state)
            else:
                raw = self._call_llm(ins, ctx, dl if dl else None, _state=state)

            try:
                parsed = self.parse_response(raw)
                if ok in parsed:
                    dl[ok] = parsed[ok]
                elif "deliverables" in parsed and ok in parsed["deliverables"]:
                    dl[ok] = parsed["deliverables"][ok]
                else:
                    dl[ok] = parsed
                logger.info(f"[{self.agent_id}] {sn}: OK")
                formatted = _format_deliverable(ok, dl[ok])
                _post_to_discord_sync(ch, f"✅ **{self.agent_name}** — **{sn}**\n\n{formatted}")
            except json.JSONDecodeError as e:
                logger.error(f"[{self.agent_id}] {sn} JSON fail: {e}")
                err_msg = f"> **Erreur de parsing JSON**: {str(e)[:150]}\n\n"
                dl[ok] = err_msg + (raw[:8000] if raw.strip() else "*Aucun contenu retourne par le LLM*")
                _post_to_discord_sync(ch, f"⚠️ **{self.agent_name}** — **{sn}** : output brut preserve.")
            self._evt("step_end", state, step=i, step_name=sn, success=ok in dl)

        _post_to_discord_sync(ch, f"📋 **{self.agent_name}** — {len(self.steps)} etapes terminees ✅")
        return {
            "agent_id": self.agent_id, "status": "complete", "confidence": 0.85,
            "deliverables": dl, "steps_completed": len(self.steps),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _run_single(self, state):
        ctx = self.build_context(state)
        ch = self._get_channel_id(state)

        if self.use_tools:
            raw = self._call_llm_with_tools(ctx.get("task", "Produis ton livrable."), ctx, _state=state)
        else:
            raw = self._call_llm(ctx.get("task", "Produis ton livrable."), ctx, _state=state)

        try:
            output = self.parse_response(raw)
            # Si le JSON n'a pas de deliverables, tout le contenu sauf les meta-champs devient deliverables
            if "deliverables" not in output:
                meta_keys = {"agent_id", "status", "confidence", "timestamp", "parse_note"}
                deliverables = {k: v for k, v in output.items() if k not in meta_keys}
                if deliverables:
                    output["deliverables"] = deliverables
                else:
                    output["deliverables"] = {"response": raw[:8000]}
        except (json.JSONDecodeError, ValueError):
            # Pas du JSON — c'est une reponse texte libre (typique apres ReAct avec tools)
            output = {
                "agent_id": self.agent_id, "status": "complete", "confidence": 0.8,
                "deliverables": {"response": raw[:8000]},
            }

        output.setdefault("status", "complete")
        output["agent_id"] = self.agent_id
        output["timestamp"] = datetime.now(timezone.utc).isoformat()

        s = output.get("status", "unknown")
        d = output.get("deliverables", {})

        if s == "complete":
            msg = _format_output_for_discord(self.agent_name, d)
            _post_to_discord_sync(ch, msg)
        elif s == "blocked":
            reason = output.get("error", "")
            if not reason and isinstance(d, dict):
                reason = d.get("raw_output", d.get("response", ""))
            if not isinstance(reason, str):
                reason = json.dumps(reason, ensure_ascii=False, default=str)
            _post_to_discord_sync(ch, f"⚠️ **{self.agent_name}** bloque : {reason[:500]}")
        else:
            _post_to_discord_sync(ch, f"ℹ️ **{self.agent_name}** — status: {s}")

        return output

    # ── Point d'entree ───────────────────────────────────────────────────────

    def _evt(self, event_type, state, **data):
        """Emet un event sur le bus."""
        bus.emit(Event(event_type, agent_id=self.agent_id,
                       thread_id=state.get("_thread_id", ""),
                       team_id=state.get("_team_id", ""), data=data))

    def _run_deliverable(self, state, dispatch_info):
        """Run a single deliverable: one step with enriched prompt."""
        from agents.shared.rate_limiter import throttled_invoke
        from agents.shared.langfuse_setup import get_langfuse_callbacks
        from agents.shared.agent_loader import load_agent_supplementary_prompts

        ctx = self.build_context(state)
        ch = self._get_channel_id(state)
        step_name = dispatch_info.get("step_name", dispatch_info.get("step", ""))
        step_key = dispatch_info.get("step", "")
        instruction = dispatch_info.get("instruction", "")

        if not instruction:
            return {"agent_id": self.agent_id, "step": step_key,
                    "status": "blocked", "error": "No instruction for this deliverable",
                    "timestamp": datetime.now(timezone.utc).isoformat()}

        logger.info(f"[{self.agent_id}] Deliverable: {step_key} — {step_name}")
        _post_to_discord_sync(ch, f"⏳ **{self.agent_name}** — livrable **{step_name}** ({step_key})...")

        # Enrich system prompt with assign/unassign
        enriched_prompt = self.system_prompt
        supplementary = load_agent_supplementary_prompts(self.agent_id)
        if supplementary:
            enriched_prompt += "\n\n" + supplementary

        # Build messages
        uc = f"Contexte:\n```json\n{json.dumps(ctx, indent=2, default=str)}\n```\n\n"
        # Include previously completed deliverables as context
        prev = {k: v.get("deliverables", {}) for k, v in state.get("agent_outputs", {}).items()
                if isinstance(v, dict) and v.get("status") == "complete" and v.get("deliverables")}
        if prev:
            ps = json.dumps(prev, indent=2, default=str, ensure_ascii=False)
            if len(ps) > 15000:
                ps = ps[:15000] + "\n...(tronque)"
            uc += f"Livrables precedents:\n```json\n{ps}\n```\n\n"
        lang = ctx.get("project_metadata", {}).get("language", "fr")
        lang_label = {"fr": "français", "en": "English", "es": "español", "de": "Deutsch"}.get(lang, lang)
        uc += f"Mission: {instruction}\n\nRedige tout le contenu en {lang_label}."

        msgs = [
            {"role": "system", "content": enriched_prompt},
            {"role": "user", "content": uc},
        ]

        self._evt("llm_call_start", state, provider=self.llm_provider, model=self.model,
                   messages_count=len(msgs), deliverable=step_key)

        # For remark re-invocations (long instruction with deliverable context), skip tools
        is_remark = "LIVRABLE ACTUEL" in instruction or "REMARQUES HUMAINES" in instruction
        if self.use_tools and not is_remark:
            # Temporarily swap system_prompt to include assign/unassign
            original_prompt = self.system_prompt
            self.system_prompt = enriched_prompt
            try:
                raw = self._call_llm_with_tools(instruction, ctx, None, _state=state)
            finally:
                self.system_prompt = original_prompt
        else:
            llm = self.get_llm()
            r = throttled_invoke(llm, msgs, provider_name=self.llm_provider,
                                 model=self.model, callbacks=self._get_callbacks())
            raw = r.content if isinstance(r.content, str) else str(r.content)

        try:
            parsed = self.parse_response(raw)
            dl = {}
            if step_key in parsed:
                dl[step_key] = parsed[step_key]
            elif "deliverables" in parsed and step_key in parsed["deliverables"]:
                dl[step_key] = parsed["deliverables"][step_key]
            else:
                dl[step_key] = parsed
            formatted = _format_deliverable(step_key, dl[step_key])
            _post_to_discord_sync(ch, f"✅ **{self.agent_name}** — **{step_name}**\n\n{formatted}")
        except json.JSONDecodeError as e:
            err_msg = f"> **Erreur de parsing JSON**: {str(e)[:150]}\n\n"
            dl = {step_key: err_msg + (raw[:8000] if raw.strip() else "*Aucun contenu retourne par le LLM*")}
            _post_to_discord_sync(ch, f"⚠️ **{self.agent_name}** — **{step_name}** : output brut preserve.")

        return {
            "agent_id": self.agent_id, "step": step_key,
            "status": "complete", "confidence": 0.85,
            "deliverables": dl,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def __call__(self, state):
        try:
            self._current_state = state

            # Override system prompt if onboarding agent_prompts are provided
            agent_prompts = state.get("_agent_prompts", {})
            if agent_prompts and self.agent_id in agent_prompts:
                override = agent_prompts[self.agent_id]
                if override:
                    logger.info(f"[{self.agent_id}] Using onboarding prompt override ({len(override)} chars)")
                    self.system_prompt = override

            # Set project_slug for RAG tools context
            slug = state.get("project_slug", "")
            if slug:
                try:
                    from agents.shared.rag_service import set_project_slug
                    set_project_slug(slug)
                except ImportError:
                    pass

            # Filter tools based on chat config (agent_tools) or inject_rag mode
            agent_tools_map = state.get("_agent_tools", {})
            allowed_tool_names = agent_tools_map.get(self.agent_id)  # None = no restriction

            if allowed_tool_names is not None and self._tools:
                # Keep only allowed MCP tools + rag_search + ask_human (always available)
                always_allowed = {"rag_search", "rag_index", "ask_human"}
                allowed_set = set(allowed_tool_names) | always_allowed
                before = len(self._tools)
                self._tools = [t for t in self._tools if t.name in allowed_set]
                logger.info(f"[{self.agent_id}] Chat tools filter: {before} -> {len(self._tools)} tools (allowed: {sorted(allowed_set)})")
            elif state.get("_inject_rag") and self._tools:
                # inject_rag without agent_tools: keep only ask_human + rag
                before = len(self._tools)
                self._tools = [t for t in self._tools if t.name in ("ask_human", "rag_search", "rag_index")]
                logger.info(f"[{self.agent_id}] inject_rag mode — kept rag + ask_human ({before} -> {len(self._tools)} tools)")

            # Deliverable-based dispatch: run a single step
            dispatch_info = state.get("_deliverable_dispatch")
            if dispatch_info:
                step_key = dispatch_info.get("step", "")
                output_key = f"{self.agent_id}:{step_key}"
                logger.info(f"[{self.agent_id}] Deliverable dispatch: {output_key}")
                self._evt("agent_start", state, steps=1, use_tools=self.use_tools, deliverable=step_key)
                output = self._run_deliverable(state, dispatch_info)

                ao = dict(state.get("agent_outputs", {}))
                ao[output_key] = output
                state["agent_outputs"] = ao
                msgs = list(state.get("messages", []))
                msgs.append(("assistant", f"[{output_key}] status={output.get('status')}"))
                state["messages"] = msgs
                logger.info(f"[{output_key}] Done — status={output.get('status')}")
                self._evt("agent_complete", state, status=output.get("status", "complete"),
                          deliverables=output.get("deliverables", {}))
                return state

            logger.info(f"[{self.agent_id}] Start — steps={len(self.steps)}, tools={self.use_tools}")
            self._evt("agent_start", state, steps=len(self.steps), use_tools=self.use_tools)
            output = self._run_steps(state) if self.steps else self._run_single(state)

            # Human gate — demander validation si configure
            if self.requires_approval and output.get("status") == "complete":
                ch = self._get_channel_id(state)
                logger.info(f"[{self.agent_id}] Requesting human approval...")
                self._evt("human_gate_requested", state, summary=f"{self.agent_name} en attente de validation")
                _post_to_discord_sync(ch, f"🔒 **{self.agent_name}** a termine. Validation en attente dans #human-review...")

                try:
                    from agents.shared.human_gate import request_approval_sync
                    deliverables = output.get("deliverables", {})
                    summary = f"{self.agent_name} a produit : {', '.join(deliverables.keys())}"
                    details = ""
                    for k in list(deliverables.keys())[:3]:
                        details += f"**{k}** : {_format_deliverable(k, deliverables[k])[:500]}\n\n"

                    approval = request_approval_sync(
                        agent_name=self.agent_name,
                        summary=summary,
                        details=details,
                        timeout=1800,
                        thread_id=state.get("_thread_id", ""),
                        team_id=state.get("_team_id", "default"),
                    )

                    if approval["approved"]:
                        output["human_approval"] = {"status": "approved", "reviewer": approval["reviewer"]}
                        self._evt("human_gate_responded", state, decision="approved", reviewer=approval["reviewer"])
                        _post_to_discord_sync(ch, f"✅ **{self.agent_name}** approuve par {approval['reviewer']}")
                        logger.info(f"[{self.agent_id}] Approved by {approval['reviewer']}")
                    elif approval["timed_out"]:
                        output["human_approval"] = {"status": "timeout"}
                        output["status"] = "pending_review"
                        self._evt("human_gate_responded", state, decision="timeout")
                        _post_to_discord_sync(ch, f"⏰ **{self.agent_name}** — timeout, en attente de review")
                        logger.warning(f"[{self.agent_id}] Approval timeout")
                    else:
                        output["human_approval"] = {"status": "revision", "feedback": approval["response"], "reviewer": approval["reviewer"]}
                        output["status"] = "revision_requested"
                        self._evt("human_gate_responded", state, decision="revision", reviewer=approval["reviewer"])
                        _post_to_discord_sync(ch, f"🔄 **{self.agent_name}** — revision demandee par {approval['reviewer']}: {approval['response'][:200]}")
                        logger.info(f"[{self.agent_id}] Revision requested: {approval['response'][:100]}")
                except Exception as e:
                    logger.error(f"[{self.agent_id}] Human gate error: {e}")
                    output["human_approval"] = {"status": "error", "detail": str(e)}

            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = output
            state["agent_outputs"] = ao

            msgs = list(state.get("messages", []))
            msgs.append(("assistant", f"[{self.agent_id}] status={output.get('status')}"))
            state["messages"] = msgs

            logger.info(f"[{self.agent_id}] Done — status={output.get('status')}")
            self._evt("agent_complete", state,
                      status=output.get("status", "complete"),
                      deliverables=output.get("deliverables", {}))
            return state
        except Exception as e:
            logger.error(f"[{self.agent_id}] EXC: {e}", exc_info=True)
            self._evt("agent_error", state, error=str(e))
            ch = self._get_channel_id(state)
            _post_to_discord_sync(ch, f"❌ **{self.agent_name}** erreur : {str(e)[:300]}")

            ao = dict(state.get("agent_outputs", {}))
            ao[self.agent_id] = {
                "agent_id": self.agent_id, "status": "blocked",
                "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            state["agent_outputs"] = ao
            return state
