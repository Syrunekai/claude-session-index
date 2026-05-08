"""Configuration resolution for claude-session-index.

Priority order:
1. Function arguments (passed directly)
2. Environment variables (SESSION_INDEX_PROJECTS, SESSION_INDEX_DB, SESSION_INDEX_TOPICS)
3. Config file ($XDG_CONFIG_HOME/claude-session-index/config.toml)
4. Sensible defaults

Path conventions (XDG Base Directory Specification):
- Config: $XDG_CONFIG_HOME/claude-session-index/  (default: ~/.config/...)
- Cache:  $XDG_CACHE_HOME/claude-session-index/   (default: ~/.cache/...)
- Topics live under ~/.claude/session-topics/ — that is Claude's namespace,
  not ours, and existing hooks reference it.

Schema version: every config file should declare a `schema_version`. When
the tool's CURRENT_SCHEMA_VERSION moves ahead of the user's file, defaults
fill in any new keys silently and a one-time warning points at the latest
config.example.toml for reference.
"""

import os
import stat
import sys
import tomllib
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
    "auto_reindex_time": 60,
}

CONFIG_FILE = _xdg_config_home() / _APP_DIR_NAME / "config.toml"

# Bump when the keys recognized in the config file change. Older
# config files keep working — defaults fill in any missing keys —
# but a one-time warning nudges the user to refresh from the
# latest config.example.toml.
CURRENT_SCHEMA_VERSION = 2

CONFIG_TEMPLATE = """\
# Configuration for claude-session-index
#
# Edit this file to customize behavior. All keys have sensible defaults
# and can be omitted. Lines starting with # are comments.

# Schema version. Tracks the shape of this file. If you keep an old
# config after upgrading the tool, defaults are used silently for any
# newly added keys and a one-time warning will point you at the latest
# config.example.toml.
schema_version = 2

# Where Claude Code session JSONL files live. Override only if Claude
# stores sessions somewhere unusual.
# projects_dir = "~/.claude/projects"

# SQLite index database location. Defaults to a path under XDG_CACHE_HOME.
# db_path = "~/.cache/claude-session-index/sessions.db"

# Hook-captured topic timeline directory. This is Claude Code's namespace,
# not ours — change only if you have moved Claude's data.
# topics_dir = "~/.claude/session-topics"

# How long (in minutes) the index can go un-refreshed before the next
# `sessions` command auto-runs an incremental re-index. Cheap for active
# sessions (only the changed ones get re-parsed) but adds a sweep cost
# proportional to your total session count. Set to 0 to disable and
# manage indexing yourself with `sessions index`. Default: 60.
# auto_reindex_time = 60

# Optional: list of client names. Sessions whose prompts mention any of
# these names get auto-tagged with the matching client. Used by
# `sessions analytics --client <name>`.
clients = []

# Optional: map raw project directory names to friendlier display names.
# The directory name is what Claude Code creates from the project path —
# typically a slug like "-Users-foo-Projects-myapp".
[project_names]
# "-Users-foo-Projects-myapp" = "myapp"
"""

_cached_config: Optional[dict] = None
_legacy_notice_emitted = False
_schema_warning_emitted = False


def secure_mkdir(path, mode: int = 0o700) -> None:
    """Create directory with restrictive permissions, healing existing dirs.

    The DB and config dirs hold session content that can include sensitive
    data (paths, code, anything ever discussed in a Claude session). Default
    umask on most systems leaves these world-readable, which is wrong on a
    multi-user box. This always ends with mode 0o700 if at all possible.
    """
    path = Path(path)
    if path.exists():
        try:
            current = stat.S_IMODE(path.stat().st_mode)
            if current != mode:
                path.chmod(mode)
        except OSError:
            pass
    else:
        path.mkdir(parents=True, mode=mode, exist_ok=True)


def secure_chmod_file(path, mode: int = 0o600) -> None:
    """Heal file permissions if existing file has wrong mode."""
    path = Path(path)
    if path.exists():
        try:
            current = stat.S_IMODE(path.stat().st_mode)
            if current != mode:
                path.chmod(mode)
        except OSError:
            pass


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
    """Load config from CONFIG_FILE if it exists, returning {} on any failure."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "rb") as f:
                return tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError):
            pass
    return {}


def _maybe_emit_schema_warning(file_config: dict) -> None:
    """One-time warning when the user's config schema_version doesn't match.

    Cases:
    - No schema_version field    -> "pre-versioning, refresh from example"
    - schema_version < current   -> "out of date, refresh from example"
    - schema_version > current   -> "newer than tool supports"
    Matching version is silent.
    """
    global _schema_warning_emitted
    if _schema_warning_emitted:
        return
    if not CONFIG_FILE.exists():
        return  # No file = no schema concern; defaults apply silently

    user_version = file_config.get("schema_version")
    if user_version == CURRENT_SCHEMA_VERSION:
        return

    if user_version is None:
        msg = (
            f"warning: config at {CONFIG_FILE} has no schema_version. "
            f"Latest is v{CURRENT_SCHEMA_VERSION}. Defaults apply for any "
            "missing keys. See config.example.toml."
        )
    elif user_version < CURRENT_SCHEMA_VERSION:
        msg = (
            f"warning: config schema is v{user_version}, latest is "
            f"v{CURRENT_SCHEMA_VERSION}. Defaults apply for any missing "
            "keys. See config.example.toml."
        )
    else:
        msg = (
            f"warning: config schema is v{user_version} but this tool only "
            f"supports up to v{CURRENT_SCHEMA_VERSION}. Some keys may not be "
            "recognized."
        )

    _schema_warning_emitted = True
    print(msg, file=sys.stderr)


def get_config() -> dict:
    """Resolve config from all sources. Result is cached after first call."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    # Start with defaults
    config = dict(DEFAULTS)

    # Layer on config file
    file_config = _load_config_file()
    _maybe_emit_schema_warning(file_config)
    for key, value in file_config.items():
        if key == "schema_version":
            continue  # Metadata, not a runtime setting
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
    secure_mkdir(p.parent, 0o700)
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

    secure_mkdir(CONFIG_FILE.parent, 0o700)
    CONFIG_FILE.write_text(CONFIG_TEMPLATE)
    secure_chmod_file(CONFIG_FILE, 0o600)
    return True


def ensure_indexed(db_path: Path = None) -> bool:
    """Auto-index on first use, and refresh stale indexes.

    On an empty/missing DB, runs a full backfill. On a populated DB whose
    `last_indexed_at` is older than `auto_reindex_time` minutes ago, runs
    an incremental refresh. Setting `auto_reindex_time = 0` disables the
    staleness check (manual indexing only). Returns True if any indexing
    was triggered.
    """
    import sqlite3
    import time

    if db_path is None:
        db_path = get_db_path()

    needs_backfill = False
    needs_refresh = False
    last_indexed_at: Optional[int] = None

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
                if count == 0:
                    needs_backfill = True
                else:
                    try:
                        row = conn.execute(
                            "SELECT value FROM metadata WHERE key='last_indexed_at'"
                        ).fetchone()
                        last_indexed_at = int(row[0]) if row else None
                    except sqlite3.OperationalError:
                        last_indexed_at = None  # metadata table missing — pre-v2 DB
            else:
                needs_backfill = True
            conn.close()
        except Exception:
            needs_backfill = True

    if not needs_backfill:
        threshold_minutes = int(get_config().get("auto_reindex_time", 0) or 0)
        if threshold_minutes > 0:
            now = int(time.time())
            if last_indexed_at is None or (now - last_indexed_at) >= threshold_minutes * 60:
                needs_refresh = True

    if not (needs_backfill or needs_refresh):
        return False

    try:
        from session_index.indexer import SessionIndexer
    except ImportError:
        try:
            from .indexer import SessionIndexer
        except ImportError:
            from indexer import SessionIndexer

    indexer = SessionIndexer(db_path=db_path)
    indexer.connect()
    try:
        if needs_backfill:
            print("\n  First run — indexing all your sessions...")
            print("  (This only happens once.)\n")
            indexer.backfill_all()
        else:
            indexer.index_incremental()
    finally:
        indexer.close()
    return True
