"""Configuration resolution for claude-session-index.

Priority order:
1. Function arguments (passed directly)
2. Environment variables (SESSION_INDEX_PROJECTS, SESSION_INDEX_DB, SESSION_INDEX_TOPICS)
3. Config file ($XDG_CONFIG_HOME/claude-session-index/config.json)
4. Sensible defaults

Path conventions (XDG Base Directory Specification):
- Config: $XDG_CONFIG_HOME/claude-session-index/  (default: ~/.config/...)
- Cache:  $XDG_CACHE_HOME/claude-session-index/   (default: ~/.cache/...)
- Topics live under ~/.claude/session-topics/ — that is Claude's namespace,
  not ours, and existing hooks reference it.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional


def _xdg_cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))


_APP_DIR_NAME = "claude-session-index"
_LEGACY_DIR = Path.home() / ".session-index"

DEFAULTS = {
    "projects_dir": str(Path.home() / ".claude" / "projects"),
    "db_path": str(_xdg_cache_home() / _APP_DIR_NAME / "sessions.db"),
    "topics_dir": str(Path.home() / ".claude" / "session-topics"),
    "clients": [],
    "project_names": {},
}

CONFIG_FILE = _xdg_config_home() / _APP_DIR_NAME / "config.json"

_cached_config: Optional[dict] = None
_legacy_notice_emitted = False


def _maybe_emit_legacy_path_notice():
    """One-time notice if legacy ~/.session-index/ paths still exist.

    The pre-fork upstream stored everything under ~/.session-index/. This fork
    moved to XDG-compliant paths. If a user is upgrading from upstream, their
    old DB and config are still on disk but no longer used. Tell them once so
    they can clean up.
    """
    global _legacy_notice_emitted
    if _legacy_notice_emitted:
        return

    legacy_db = _LEGACY_DIR / "sessions.db"
    legacy_config = _LEGACY_DIR / "config.json"

    found = []
    if legacy_db.exists():
        found.append(f"  - {legacy_db}")
    if legacy_config.exists():
        found.append(f"  - {legacy_config}")

    if not found:
        return

    _legacy_notice_emitted = True
    new_db = Path(DEFAULTS["db_path"])
    print(
        "notice: legacy ~/.session-index/ paths detected:\n"
        + "\n".join(found) + "\n"
        f"This fork uses XDG-compliant paths. A fresh index will be built at "
        f"{new_db}.\n"
        f"After verifying things work, remove the legacy directory: "
        f"rm -rf {_LEGACY_DIR}",
        file=sys.stderr,
    )


def _load_config_file() -> dict:
    """Load config from ~/.session-index/config.json if it exists."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def get_config() -> dict:
    """Resolve config from all sources. Result is cached after first call."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    # Start with defaults
    config = dict(DEFAULTS)

    # Layer on config file
    file_config = _load_config_file()
    for key, value in file_config.items():
        if key in config and value is not None:
            config[key] = value

    # Layer on environment variables
    env_map = {
        "SESSION_INDEX_PROJECTS": "projects_dir",
        "SESSION_INDEX_DB": "db_path",
        "SESSION_INDEX_TOPICS": "topics_dir",
    }
    for env_key, config_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            config[config_key] = val

    _cached_config = config
    return config


def get_projects_dir(override: str = None) -> Path:
    """Get projects directory path."""
    if override:
        return Path(override).expanduser()
    return Path(get_config()["projects_dir"]).expanduser()


def get_db_path(override: str = None) -> Path:
    """Get database path, creating parent directory if needed."""
    _maybe_emit_legacy_path_notice()
    if override:
        p = Path(override).expanduser()
    else:
        p = Path(get_config()["db_path"]).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_topics_dir(override: str = None) -> Path:
    """Get topics directory path."""
    if override:
        return Path(override).expanduser()
    return Path(get_config()["topics_dir"]).expanduser()


def get_clients() -> list[str]:
    """Get list of known client names (optional — used for auto-detection)."""
    return get_config().get("clients", [])


def get_project_names() -> dict[str, str]:
    """Get project directory → friendly name mapping.

    If not configured, auto-generates from directory names:
    '-Users-lee-CC-LFI' → 'LFI'
    '-Users-foo-projects-myapp' → 'myapp'
    """
    configured = get_config().get("project_names", {})
    if configured:
        return configured

    # Auto-generate from directory names
    projects_dir = get_projects_dir()
    mapping = {}
    if projects_dir.exists():
        for d in projects_dir.iterdir():
            if d.is_dir():
                name = d.name
                # Take the last meaningful segment
                parts = [p for p in name.split("-") if p]
                if parts:
                    # Use last 1-2 segments as friendly name
                    friendly = " ".join(parts[-2:]) if len(parts) > 1 else parts[-1]
                    mapping[name] = friendly

    return mapping


def init_config():
    """Create a default config file if one doesn't exist."""
    if CONFIG_FILE.exists():
        return False

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(DEFAULTS, indent=2) + "\n")
    return True


def ensure_indexed(db_path: Path = None) -> bool:
    """Auto-index on first use if database is empty or missing.

    Returns True if backfill was triggered.
    """
    import sqlite3

    if db_path is None:
        db_path = get_db_path()

    needs_backfill = False
    if not db_path.exists():
        needs_backfill = True
    else:
        try:
            conn = sqlite3.connect(str(db_path))
            has_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
            ).fetchone()
            if has_table:
                count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                needs_backfill = (count == 0)
            else:
                needs_backfill = True
            conn.close()
        except Exception:
            needs_backfill = True

    if needs_backfill:
        print("\n  First run — indexing all your sessions...")
        print("  (This only happens once.)\n")
        try:
            from session_index.indexer import SessionIndexer
        except ImportError:
            try:
                from .indexer import SessionIndexer
            except ImportError:
                from indexer import SessionIndexer
        indexer = SessionIndexer(db_path=db_path)
        indexer.connect()
        indexer.backfill_all()
        indexer.close()
        return True
    return False
