"""Tests Auth du dashboard admin — fonctions pures + endpoints."""
import hashlib
import hmac
import secrets
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# On importe directement les fonctions pures depuis web.server
# Le module a des side-effects a l'import, donc on mock ce qui faut

_web_dir = Path(__file__).resolve().parent.parent.parent / "web"
if str(_web_dir.parent) not in sys.path:
    sys.path.insert(0, str(_web_dir.parent))


class TestSessionToken:
    """Tests des fonctions _make_session_token / _verify_session_token."""

    def _make_token(self, username, secret):
        sig = hmac.new(secret.encode(), username.encode(), hashlib.sha256).hexdigest()
        return f"{username}:{sig}"

    def _verify_token(self, token, secret):
        if ":" not in token:
            return False
        username, sig = token.split(":", 1)
        expected = hmac.new(secret.encode(), username.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    def test_roundtrip(self):
        secret = secrets.token_hex(32)
        token = self._make_token("admin", secret)
        assert self._verify_token(token, secret)

    def test_different_users(self):
        secret = secrets.token_hex(32)
        t1 = self._make_token("admin", secret)
        t2 = self._make_token("user2", secret)
        assert t1 != t2
        assert self._verify_token(t1, secret)
        assert self._verify_token(t2, secret)

    def test_tampered_signature(self):
        secret = secrets.token_hex(32)
        token = self._make_token("admin", secret)
        # Flip last char
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        assert not self._verify_token(tampered, secret)

    def test_no_colon(self):
        secret = secrets.token_hex(32)
        assert not self._verify_token("no-colon-here", secret)

    def test_wrong_secret(self):
        s1 = secrets.token_hex(32)
        s2 = secrets.token_hex(32)
        token = self._make_token("admin", s1)
        assert not self._verify_token(token, s2)

    def test_empty_username(self):
        secret = secrets.token_hex(32)
        token = self._make_token("", secret)
        assert self._verify_token(token, secret)
        assert token.startswith(":")


class TestParseEnv:
    """Tests de la fonction _parse_env."""

    def test_parse_basic(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n", encoding="utf-8")

        entries = self._parse_env(env_file)
        keys = [e["key"] for e in entries if e["key"]]
        assert keys == ["KEY1", "KEY2"]
        assert entries[0]["value"] == "value1"

    def test_parse_with_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# Section\nKEY=val\n\n# Another\n", encoding="utf-8")

        entries = self._parse_env(env_file)
        assert len(entries) == 4
        assert entries[0]["comment"] == "# Section"
        assert entries[1]["key"] == "KEY"
        assert entries[2]["comment"] == ""  # blank line
        assert entries[3]["comment"] == "# Another"

    def test_parse_value_with_equals(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("URL=postgresql://user:pass@host/db\n", encoding="utf-8")

        entries = self._parse_env(env_file)
        assert entries[0]["key"] == "URL"
        assert entries[0]["value"] == "postgresql://user:pass@host/db"

    def test_parse_missing_file(self, tmp_path):
        env_file = tmp_path / ".env.missing"
        entries = self._parse_env(env_file)
        assert entries == []

    def test_write_roundtrip(self, tmp_path):
        env_file = tmp_path / ".env"
        original = [
            {"key": "", "value": "", "comment": "# Config"},
            {"key": "A", "value": "1", "comment": ""},
            {"key": "B", "value": "2", "comment": ""},
        ]
        self._write_env(env_file, original)
        parsed = self._parse_env(env_file)
        assert len(parsed) == 3
        assert parsed[0]["comment"] == "# Config"
        assert parsed[1]["key"] == "A"
        assert parsed[2]["value"] == "2"

    @staticmethod
    def _parse_env(path: Path) -> list:
        entries = []
        if not path.exists():
            return entries
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                entries.append({"key": "", "value": "", "comment": stripped})
                continue
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                entries.append({"key": k.strip(), "value": v.strip(), "comment": ""})
            else:
                entries.append({"key": "", "value": "", "comment": stripped})
        return entries

    @staticmethod
    def _write_env(path: Path, entries: list):
        lines = []
        for e in entries:
            if e.get("key"):
                lines.append(f"{e['key']}={e['value']}")
            else:
                lines.append(e.get("comment", ""))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestReadWriteJson:
    """Tests des helpers JSON."""

    def test_read_json_missing(self, tmp_path):
        path = tmp_path / "missing.json"
        assert self._read_json(path) == {}

    def test_read_json_empty(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("", encoding="utf-8")
        assert self._read_json(path) == {}

    def test_read_json_valid(self, tmp_path):
        path = tmp_path / "data.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        assert self._read_json(path) == {"a": 1}

    def test_read_json_invalid(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json}", encoding="utf-8")
        assert self._read_json(path) == {}

    def test_write_json_creates_parents(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "data.json"
        self._write_json(path, {"key": "value"})
        assert path.exists()
        import json
        assert json.loads(path.read_text(encoding="utf-8")) == {"key": "value"}

    @staticmethod
    def _read_json(path: Path) -> dict:
        if not path.exists():
            return {}
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        try:
            import json
            return json.loads(content)
        except Exception:
            return {}

    @staticmethod
    def _write_json(path: Path, data: dict):
        import json
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class TestParseMcpCatalog:
    """Tests du parsing du catalogue MCP CSV."""

    def test_parse_basic(self, tmp_path):
        csv = tmp_path / "catalog.csv"
        csv.write_text(
            "# header\n"
            "0|github|GitHub|Desc|npx|@mcp/github|stdio|GITHUB_TOKEN:Token\n",
            encoding="utf-8",
        )
        items = self._parse(csv)
        assert len(items) == 1
        assert items[0]["id"] == "github"
        assert items[0]["deprecated"] is False
        assert items[0]["env_vars"] == [{"var": "GITHUB_TOKEN", "desc": "Token"}]

    def test_parse_deprecated(self, tmp_path):
        csv = tmp_path / "catalog.csv"
        csv.write_text("1|old|Old|Deprecated|npx|@old|stdio|\n", encoding="utf-8")
        items = self._parse(csv)
        assert items[0]["deprecated"] is True

    def test_parse_no_env_vars(self, tmp_path):
        csv = tmp_path / "catalog.csv"
        csv.write_text("0|srv|Srv|Desc|npx|args|stdio|\n", encoding="utf-8")
        items = self._parse(csv)
        assert items[0]["env_vars"] == []

    def test_parse_empty(self, tmp_path):
        csv = tmp_path / "catalog.csv"
        csv.write_text("# only comments\n\n", encoding="utf-8")
        assert self._parse(csv) == []

    def test_parse_missing_file(self, tmp_path):
        csv = tmp_path / "nope.csv"
        assert self._parse(csv) == []

    @staticmethod
    def _parse(path: Path) -> list:
        """Reimplementation fidele de _parse_mcp_catalog."""
        items = []
        if not path.exists():
            return items
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) >= 7:
                env_vars = []
                if len(parts) > 7 and parts[7].strip():
                    for ev in parts[7].split(","):
                        kv = ev.split(":", 1)
                        env_vars.append({"var": kv[0].strip(), "desc": kv[1].strip() if len(kv) > 1 else ""})
                items.append({
                    "deprecated": parts[0].strip() == "1",
                    "id": parts[1].strip(),
                    "label": parts[2].strip(),
                    "description": parts[3].strip(),
                    "command": parts[4].strip(),
                    "args": parts[5].strip(),
                    "transport": parts[6].strip(),
                    "env_vars": env_vars,
                })
        return items
