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
    pipeline_steps = []
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

        # Fallback minimal
        logger.warning(f"[{self.agent_id}] No prompt file found — using fallback")
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
            """Pose une question a l'humain via Discord et attend sa reponse.
            Utilise ce tool quand tu as besoin d'une clarification, d'un choix,
            ou d'une information que seul l'humain peut fournir.
            Args:
                question: La question a poser
                context: Contexte optionnel pour aider l'humain a repondre
            Returns:
                La reponse de l'humain ou un message de timeout
            """
            from agents.shared.agent_conversation import ask_human_sync
            channel_id = os.getenv("DISCORD_CHANNEL_COMMANDS", "")
            current_state = getattr(agent_ref, '_current_state', {})
            result = ask_human_sync(
                agent_ref.agent_name, question, channel_id, context, timeout=1800,
                thread_id=current_state.get("_thread_id", ""),
                team_id=current_state.get("_team_id", "default"),
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
        raise json.JSONDecodeError("No valid JSON found in response", raw[:200], 0)

    # ── Appels LLM ───────────────────────────────────────────────────────────

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
        uc += f"Instruction: {instruction}\n\nReponds UNIQUEMENT en JSON valide. Redige tout le contenu en {lang_label}."
        msgs = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": uc},
        ]
        st = _state or {}
        bus.emit(Event("llm_call_start", agent_id=self.agent_id,
                        thread_id=st.get("_thread_id", ""), team_id=st.get("_team_id", ""),
                        data={"provider": self.llm_provider, "model": self.model, "messages_count": len(msgs)}))
        r = throttled_invoke(llm, msgs, provider_name=self.llm_provider, model=self.model)
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

        for iteration in range(10):
            bus.emit(Event("llm_call_start", agent_id=self.agent_id,
                            thread_id=st.get("_thread_id", ""), team_id=st.get("_team_id", ""),
                            data={"provider": self.llm_provider, "model": self.model,
                                  "messages_count": len(msgs), "iteration": iteration + 1}))
            resp = throttled_invoke(llm_t, msgs, provider_name=self.llm_provider, model=self.model)
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
                logger.info(f"[{self.agent_id}] ReAct done — {iteration + 1} iters")
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

        last = msgs[-1]
        logger.warning(f"[{self.agent_id}] ReAct max iters")
        return last.content if hasattr(last, "content") and isinstance(last.content, str) else str(last)

    # ── Modes d'execution ────────────────────────────────────────────────────

    def _run_pipeline(self, state):
        ctx = self.build_context(state)
        ch = self._get_channel_id(state)
        dl = {}

        for i, step in enumerate(self.pipeline_steps, 1):
            sn, ins, ok = step["name"], step["instruction"], step["output_key"]
            logger.info(f"[{self.agent_id}] Pipeline {i}/{len(self.pipeline_steps)}: {sn}")
            self._evt("pipeline_step_start", state, step=i, total=len(self.pipeline_steps), step_name=sn)
            _post_to_discord_sync(ch, f"⏳ **{self.agent_name}** — etape {i}/{len(self.pipeline_steps)} : **{sn}**...")

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
                dl[ok] = {"raw": raw[:8000], "parse_error": str(e)[:100]}
                _post_to_discord_sync(ch, f"⚠️ **{self.agent_name}** — **{sn}** : output brut preserve.")
            self._evt("pipeline_step_end", state, step=i, step_name=sn, success=ok in dl)

        _post_to_discord_sync(ch, f"📋 **{self.agent_name}** — {len(self.pipeline_steps)} etapes terminees ✅")
        return {
            "agent_id": self.agent_id, "status": "complete", "confidence": 0.85,
            "deliverables": dl, "pipeline_steps_completed": len(self.pipeline_steps),
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

    def __call__(self, state):
        try:
            self._current_state = state
            logger.info(f"[{self.agent_id}] Start — pipeline={len(self.pipeline_steps)}, tools={self.use_tools}")
            self._evt("agent_start", state, pipeline_steps=len(self.pipeline_steps), use_tools=self.use_tools)
            output = self._run_pipeline(state) if self.pipeline_steps else self._run_single(state)

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
