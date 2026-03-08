"""MCP Client — Lazy install + cache global + lock par package. Utilise team_resolver."""
import json, logging, os, asyncio, subprocess, threading
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_installed_packages = set()
_install_locks = {}
_locks_mutex = threading.Lock()


def _get_lock(pkg_name):
    with _locks_mutex:
        if pkg_name not in _install_locks:
            _install_locks[pkg_name] = threading.Lock()
        return _install_locks[pkg_name]


def _load_config(filename, team_id=None):
    """Charge un JSON de config via team_resolver."""
    from agents.shared.team_resolver import load_team_json, find_global_file
    if team_id:
        data = load_team_json(team_id, filename)
        if data:
            return data
    # Fallback global
    path = find_global_file(filename)
    if path:
        with open(path) as f:
            return json.load(f)
    return {}


def _resolve_env(env_dict):
    r = {}
    for key, var_name in env_dict.items():
        val = os.getenv(var_name, os.getenv(key, ""))
        if val and val != "A_CONFIGURER":
            r[key] = val
    return r


def _ensure_npm_installed(pkg):
    if pkg in _installed_packages:
        return
    lock = _get_lock(f"npm:{pkg}")
    with lock:
        if pkg in _installed_packages:
            return
        try:
            result = subprocess.run(["npm", "list", "-g", pkg, "--depth=0"], capture_output=True, text=True, timeout=10)
            if pkg in result.stdout:
                _installed_packages.add(pkg)
                logger.info(f"MCP {pkg} already global")
                return
        except Exception:
            pass
        logger.info(f"Installing MCP {pkg} globally (first use)...")
        try:
            subprocess.run(["npm", "install", "-g", pkg], capture_output=True, text=True, timeout=120)
            _installed_packages.add(pkg)
            logger.info(f"MCP {pkg} installed globally")
        except Exception as e:
            logger.warning(f"Could not install {pkg}: {e}")


def _ensure_uv_installed(pkg):
    if pkg in _installed_packages:
        return
    lock = _get_lock(f"uv:{pkg}")
    with lock:
        if pkg in _installed_packages:
            return
        try:
            result = subprocess.run(["uv", "tool", "list"], capture_output=True, text=True, timeout=10)
            if pkg in result.stdout:
                _installed_packages.add(pkg)
                return
        except Exception:
            pass
        logger.info(f"Installing MCP {pkg} via uv (first use)...")
        try:
            subprocess.run(["uv", "tool", "install", pkg], capture_output=True, text=True, timeout=120)
            _installed_packages.add(pkg)
            logger.info(f"MCP {pkg} installed via uv")
        except Exception as e:
            logger.warning(f"Could not install {pkg}: {e}")


def _ensure_installed(cmd, args):
    if cmd == "npx":
        for i, a in enumerate(args):
            if a == "-y" and i + 1 < len(args):
                _ensure_npm_installed(args[i + 1])
                break
    elif cmd == "uvx":
        if args:
            _ensure_uv_installed(args[0])


def get_mcp_tools_sync(agent_id, team_id=None):
    try:
        loop = asyncio.new_event_loop()
        tools = loop.run_until_complete(_get_tools(agent_id, team_id))
        loop.close()
        return tools
    except Exception as e:
        logger.warning(f"[{agent_id}] MCP unavailable: {e}")
        return []


async def _get_tools(agent_id, team_id=None):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    mcp_conf = _load_config("mcp_servers.json", team_id)
    access = _load_config("agent_mcp_access.json", team_id)

    allowed = access.get(agent_id, [])
    if not allowed:
        return []

    servers = {}
    for sid in allowed:
        sc = mcp_conf.get("servers", {}).get(sid)
        if not sc or not sc.get("enabled", True):
            continue

        env = _resolve_env(sc.get("env", {}))
        missing = [k for k in sc.get("env", {}) if not env.get(k)]
        if missing:
            logger.warning(f"[{agent_id}] {sid} skip — missing: {missing}")
            continue

        cmd = sc["command"]
        args = sc["args"]
        _ensure_installed(cmd, args)

        entry = {"command": cmd, "args": args, "transport": sc.get("transport", "stdio")}
        if env:
            entry["env"] = env
        servers[sid] = entry

    if not servers:
        return []

    try:
        client = MultiServerMCPClient(servers)
        tools = await client.get_tools()
        logger.info(f"[{agent_id}] MCP: {len(tools)} tools from {list(servers.keys())}")
        return tools
    except Exception as e:
        logger.error(f"[{agent_id}] MCP error: {e}")
        return []


def get_tools_for_agent(agent_id, team_id=None):
    tools = get_mcp_tools_sync(agent_id, team_id)
    try:
        from agents.shared.rag_service import create_rag_tools
        tools.extend(create_rag_tools())
    except ImportError:
        pass
    return tools
