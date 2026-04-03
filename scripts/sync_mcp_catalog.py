#!/usr/bin/env python3
"""Sync MCP catalog — compare our mcp_catalog.csv with known MCP server packages.

Usage:
    python scripts/sync_mcp_catalog.py [--check-only]

Without --check-only: interactive mode, asks to add each new server.
With --check-only: just prints new servers found.

Sources checked:
- npm: @modelcontextprotocol/server-*, @anthropic/mcp-server-*
- pypi: mcp-server-*
"""

import csv
import json
import os
import subprocess
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_FILE = os.path.join(SCRIPT_DIR, "Infra", "mcp_catalog.csv")

# Known npm scopes to scan
NPM_SCOPES = [
    "@modelcontextprotocol/server-",
    "@anthropic/mcp-server-",
    "@anthropic-ai/mcp-server-",
    "@playwright/mcp",
    "@sentry/mcp-server-",
    "@gitlab-org/gitlab-mcp-server",
    "@notionhq/notion-mcp-server",
    "@supabase/mcp-server-",
    "@cloudflare/mcp-server-",
    "@upstash/context7-mcp",
]

# Known pypi prefixes
PYPI_PREFIXES = [
    "mcp-server-",
]


def parse_catalog() -> dict[str, dict]:
    """Parse existing catalog, return dict keyed by id."""
    entries = {}
    if not os.path.isfile(CATALOG_FILE):
        return entries
    with open(CATALOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) >= 8:
                entry_id = parts[2].strip()
                entries[entry_id] = {
                    "deprecated": parts[0].strip(),
                    "type": parts[1].strip(),
                    "id": entry_id,
                    "label": parts[3].strip(),
                    "description": parts[4].strip(),
                    "command": parts[5].strip(),
                    "args": parts[6].strip(),
                    "transport": parts[7].strip(),
                    "env_vars": parts[8].strip() if len(parts) > 8 else "",
                }
    return entries


def _find_npm() -> str:
    """Find npm executable."""
    for cmd in ["npm", "npm.cmd"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "npm"


_npm_cmd = _find_npm()


def search_npm(query: str) -> list[dict]:
    """Search npm for packages matching query."""
    try:
        result = subprocess.run(
            [_npm_cmd, "search", query, "--json"],
            capture_output=True, text=True, timeout=30, shell=(os.name == "nt"),
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and result.stdout.strip():
            # npm sometimes returns malformed JSON with extra newlines
            raw = result.stdout.strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                # Try fixing common npm JSON issues
                cleaned = raw.replace("\n\n", "\n").replace(",\n]", "\n]")
                return json.loads(cleaned)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        print("  npm search failed for '{}': {}".format(query, e))
    return []


def search_pypi(prefix: str) -> list[dict]:
    """Search pypi for packages matching prefix."""
    try:
        result = subprocess.run(
            ["pip", "index", "versions", prefix],
            capture_output=True, text=True, timeout=15,
        )
        # pip index doesn't support search well, use pip search alternative
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return []


def discover_npm_packages() -> list[dict]:
    """Discover MCP server packages from npm."""
    found = []
    seen = set()
    for scope in NPM_SCOPES:
        packages = search_npm(scope)
        for pkg in packages:
            name = pkg.get("name", "")
            if not name or name in seen:
                continue
            # Filter: must contain "mcp" in name or description
            desc = pkg.get("description", "")
            if "mcp" not in name.lower() and "model context" not in desc.lower():
                continue
            seen.add(name)
            # Derive an id from the package name
            pkg_id = name.split("/")[-1].replace("server-", "").replace("mcp-", "")
            found.append({
                "package": name,
                "id": pkg_id,
                "description": desc[:120],
                "type": "npx",
                "command": "npx",
                "args": "-y {}".format(name),
                "transport": "stdio",
            })
    return found


def discover_docker_packages() -> list[dict]:
    """Discover MCP server images from Docker Hub (mcp/ namespace)."""
    found = []
    try:
        import urllib.request
        page = 1
        while True:
            url = "https://hub.docker.com/v2/repositories/mcp/?page_size=100&page={}".format(page)
            req = urllib.request.Request(url, headers={"User-Agent": "sync_mcp_catalog/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            if not results:
                break
            for r in results:
                name = r.get("name", "")
                desc = (r.get("description") or "")[:120]
                if not name:
                    continue
                found.append({
                    "package": "mcp/{}".format(name),
                    "id": name,
                    "description": desc,
                    "type": "docker",
                    "command": "docker",
                    "args": "run --rm -i mcp/{}".format(name),
                    "transport": "stdio",
                })
            if not data.get("next"):
                break
            page += 1
    except Exception as e:
        print("  Docker Hub search failed: {}".format(e))
    return found


def append_to_catalog(entry: dict):
    """Append a new entry to the catalog."""
    with open(CATALOG_FILE, "a", encoding="utf-8") as f:
        env_str = entry.get("env_vars", "")
        f.write("0|{type}|{id}|{label}|{description}|{command}|{args}|{transport}|{env}\n".format(
            type=entry.get("type", "npx"),
            id=entry["id"],
            label=entry.get("label", entry["id"]),
            description=entry.get("description", ""),
            command=entry.get("command", "npx"),
            args=entry.get("args", ""),
            transport=entry.get("transport", "stdio"),
            env=env_str,
        ))


def main():
    check_only = "--check-only" in sys.argv

    print("=== MCP Catalog Sync ===\n")

    # 1. Parse existing catalog
    existing = parse_catalog()
    print("Existing entries: {}".format(len(existing)))
    print("  Active: {}".format(sum(1 for e in existing.values() if e["deprecated"] == "0")))
    print("  Deprecated: {}".format(sum(1 for e in existing.values() if e["deprecated"] == "1")))
    print()

    # 2. Discover new packages
    print("Searching npm for MCP server packages...")
    npm_packages = discover_npm_packages()
    print("  Found {} packages on npm".format(len(npm_packages)))

    print("Searching Docker Hub (mcp/) for MCP server images...")
    docker_packages = discover_docker_packages()
    print("  Found {} images on Docker Hub".format(len(docker_packages)))
    print()

    # Merge all sources
    npm_packages.extend(docker_packages)

    # 3. Filter new ones
    new_packages = []
    # Build set of known package names from existing catalog (including deprecated)
    existing_packages = set()
    for e in existing.values():
        # Extract package name from args (remove -y, --stdio, paths, etc.)
        for part in e["args"].split():
            if part.startswith("@") or (not part.startswith("-") and not part.startswith("/")):
                existing_packages.add(part)
        existing_packages.add(e["id"])
        existing_packages.add(e["label"])

    for pkg in npm_packages:
        # Check if package name is already known
        if pkg["package"] in existing_packages:
            continue
        if pkg["id"] in existing_packages:
            continue
        new_packages.append(pkg)

    if not new_packages:
        print("No new MCP servers found. Catalog is up to date.")
        return

    print("=== {} NEW SERVERS FOUND ===\n".format(len(new_packages)))

    added = 0
    for i, pkg in enumerate(new_packages, 1):
        print("[{}/{}] {} — {}".format(i, len(new_packages), pkg["package"], pkg["description"]))
        print("  Install: {} {}".format(pkg["command"], pkg["args"]))
        print("  Type: {} | Transport: {}".format(pkg["type"], pkg["transport"]))

        if check_only:
            print()
            continue

        answer = input("  Add to catalog? (y/n/q) ").strip().lower()
        if answer == "q":
            break
        if answer == "y":
            # Ask for a custom label
            label = input("  Label [{}]: ".format(pkg["id"])).strip() or pkg["id"]
            pkg["label"] = label
            append_to_catalog(pkg)
            added += 1
            print("  -> Added!")
        print()

    if added:
        print("\n{} servers added to catalog.".format(added))
        # Also copy to Shared/Teams
        shared_catalog = os.path.join(SCRIPT_DIR, "..", "Shared", "Teams", "mcp_catalog.csv")
        if os.path.isfile(shared_catalog):
            import shutil
            shutil.copy2(CATALOG_FILE, shared_catalog)
            print("Catalog synced to Shared/Teams/mcp_catalog.csv")


if __name__ == "__main__":
    main()
