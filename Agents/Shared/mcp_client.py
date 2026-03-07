"""MCP Client — Lazy install + cache global + lock par package."""
import json, logging, os, asyncio, subprocess, threading
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BASE = os.path.dirname(__file__)
CPATHS = [os.path.join(BASE, "..", "..", "config"), os.path.join("/app", "config")]

# Cache des packages deja installes
_installed_packages = set()

# Lock par package (evite deux installs simultanees du meme package)
_install_locks = {}
_locks_mutex = threading.Lock()


def _get_lock(pkg_name):
    """Retourne un lock dedie a ce package (thread-safe)."""
    with _locks_mutex:
        if pkg_name not in _install_locks:
            _install_locks[pkg_name] = threading.Lock()
        return _install_locks[pkg_name]


def _find(filename):
    for b in CPATHS:
        p = os.path.join(os.path.abspath(b), filename)
        if os.path.exists(p):
            return p
    return None


def _load(filename):
    p = _find(filename)
    return json.load(open(p)) if p else {}


def _resolve_env(env_dict):
    r = {}
    for key, var_name in env_dict.items():
        val = os.getenv(var_name, os.getenv(key, ""))
        if val and val != "A_CONFIGURER":
            r[key] = val
    return r


def _ensure_npm_installed(pkg):
    """Installe un package npm globalement si necessaire. Thread-safe avec lock."""
    if pkg in _installed_packages:
        return

    lock = _get_lock(f"npm:{pkg}")
    with lock:
        # Double-check apres avoir obtenu le lock
        if pkg in _installed_packages:
            return

        # Verifier si deja installe globalement
        try:
            result = subprocess.run(
                ["npm", "list", "-g", pkg, "--depth=0"],
                capture_output=True, text=True, timeout=10
            )
            if pkg in result.stdout:
                _installed_packages.add(pkg)
                logger.info(f"MCP {pkg} already global")
                return
        except Exception:
            pass

        # Installer
        logger.info(f"Installing MCP {pkg} globally (first use)...")
        try:
            subprocess.run(
                ["npm", "install", "-g", pkg],
                capture_output=True, text=True, timeout=120
            )
            _installed_packages.add(pkg)
            logger.info(f"MCP {pkg} installed globally")
        except Exception as e:
            logger.warning(f"Could not install {pkg}: {e}")


def _ensure_uv_installed(pkg):
    """Installe un package Python via uv si necessaire. Thread-safe avec lock."""
    if pkg in _installed_packages:
        return

    lock = _get_lock(f"uv:{pkg}")
    with lock:
        if pkg in _installed_packages:
            return

        # Verifier
        try:
            result = subprocess.run(
                ["uv", "tool", "list"],
                capture_output=True, text=True, timeout=10
            )
            if pkg in result.stdout:
                _installed_packages.add(pkg)
                return
        except Exception:
            pass

        # Installer
        logger.info(f"Installing MCP {pkg} via uv (first use)...")
        try:
            subprocess.run(
                ["uv", "tool", "install", pkg],
                capture_output=True, text=True, timeout=120
            )
            _installed_packages.add(pkg)
            logger.info(f"MCP {pkg} installed via uv")
        except Exception as e:
            logger.warning(f"Could not install {pkg}: {e}")


def _ensure_installed(cmd, args):
    """Installe le package globalement si necessaire."""
    if cmd == "npx":
        pkg = None
        for i, a in enumerate(args):
            if a == "-y" and i + 1 < len(args):
                pkg = args[i + 1]
                break
        if pkg:
            _ensure_npm_installed(pkg)

    elif cmd == "uvx":
        pkg = args[0] if args else None
        if pkg:
            _ensure_uv_installed(pkg)


def get_mcp_tools_sync(agent_id):
    try:
        loop = asyncio.new_event_loop()
        tools = loop.run_until_complete(_get_tools(agent_id))
        loop.close()
        return tools
    except Exception as e:
        logger.warning(f"[{agent_id}] MCP unavailable: {e}")
        return []


async def _get_tools(agent_id):
    from langchain_mcp_adapters.client import MultiServerMCPClient

    mcp_conf = _load("mcp_servers.json")
    access = _load("agent_mcp_access.json")

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

        # Lazy install (thread-safe, avec lock par package)
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


def get_tools_for_agent(agent_id):
    tools = get_mcp_tools_sync(agent_id)
    try:
        from agents.shared.rag_service import create_rag_tools
        tools.extend(create_rag_tools())
    except ImportError:
        pass
    return tools
