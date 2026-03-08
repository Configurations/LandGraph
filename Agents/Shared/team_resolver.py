"""Team Path Resolver — Source unique pour trouver les fichiers d'une equipe."""
import json
import logging
import os

logger = logging.getLogger("team_resolver")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "..")

# Chemins possibles pour trouver le dossier de config racine
CONFIGS_ROOTS = [
    os.path.join(_ROOT, "Configs"),       # dev local
    os.path.join(_HERE, "..", "config"),   # relatif au code
    os.path.join("/app", "config"),        # Docker
]

_configs_dir = None
_teams_config = None


def get_configs_dir() -> str:
    """Trouve et cache le dossier de config racine (celui qui contient teams.json)."""
    global _configs_dir
    if _configs_dir:
        return _configs_dir
    for b in CONFIGS_ROOTS:
        p = os.path.join(os.path.abspath(b), "teams.json")
        if os.path.exists(p):
            _configs_dir = os.path.abspath(b)
            logger.info(f"Configs dir: {_configs_dir}")
            return _configs_dir
    # Fallback : premier qui existe
    for b in CONFIGS_ROOTS:
        if os.path.isdir(os.path.abspath(b)):
            _configs_dir = os.path.abspath(b)
            return _configs_dir
    return ""


def get_teams_config() -> dict:
    """Charge et cache teams.json."""
    global _teams_config
    if _teams_config is not None:
        return _teams_config
    configs = get_configs_dir()
    if not configs:
        _teams_config = {"teams": []}
        return _teams_config
    path = os.path.join(configs, "teams.json")
    if not os.path.exists(path):
        _teams_config = {"teams": []}
        return _teams_config
    with open(path) as f:
        content = f.read().strip()
        if not content:
            _teams_config = {"teams": []}
            return _teams_config
        _teams_config = json.loads(content)
    return _teams_config


def get_team_info(team_id: str) -> dict:
    """Retourne les infos d'une equipe depuis teams.json."""
    config = get_teams_config()
    for team in config.get("teams", []):
        if team.get("id") == team_id:
            return team
    return {}


def get_team_dir(team_id: str) -> str:
    """Retourne le chemin absolu du dossier d'une equipe."""
    configs = get_configs_dir()
    if not configs:
        return ""
    info = get_team_info(team_id)
    directory = info.get("directory", team_id)
    return os.path.join(configs, directory)


def find_team_file(team_id: str, filename: str) -> str:
    """Trouve un fichier dans le dossier d'une equipe. Retourne '' si introuvable."""
    team_dir = get_team_dir(team_id)
    if not team_dir:
        return ""
    # Essayer le nom exact puis en minuscule
    for name in [filename, filename.lower()]:
        p = os.path.join(team_dir, name)
        if os.path.exists(p):
            return p
    return ""


def find_global_file(filename: str) -> str:
    """Trouve un fichier dans le dossier de config racine."""
    configs = get_configs_dir()
    if not configs:
        return ""
    p = os.path.join(configs, filename)
    return p if os.path.exists(p) else ""


def load_team_json(team_id: str, filename: str) -> dict:
    """Charge un fichier JSON depuis le dossier d'une equipe, avec fallback global."""
    path = find_team_file(team_id, filename)
    if not path:
        path = find_global_file(filename)
    if not path:
        return {}
    with open(path) as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)


def get_team_for_channel(channel_id: str) -> str:
    """Retourne l'ID de l'equipe pour un channel Discord."""
    config = get_teams_config()
    mapping = config.get("channel_mapping", {})
    return mapping.get(channel_id, "default")


def get_all_team_ids() -> list:
    """Liste tous les IDs d'equipes configurees."""
    config = get_teams_config()
    return [t.get("id", "") for t in config.get("teams", []) if t.get("id")]
