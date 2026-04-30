"""Setup commands for claude-session-index.

Exposed via the `sessions` CLI:
    sessions install-skill           # copy SKILL.md into ~/.claude/skills/
    sessions configure-permissions   # add cache write rule to ~/.claude/settings.json
    sessions init-config             # write a default config file
"""

import json
import sys
from datetime import datetime
from pathlib import Path

try:
    from . import config
except ImportError:
    import config


# ---------------------------------------------------------------------------
# install-skill
# ---------------------------------------------------------------------------

PACKAGE_DIR = Path(__file__).parent
SKILL_SOURCE = PACKAGE_DIR / "_skill" / "SKILL.md"
DEFAULT_SKILL_TARGET = Path.home() / ".claude" / "skills" / "session-index"


def install_skill(
    target_dir: Path = None,
    copy: bool = True,
    force: bool = False,
) -> bool:
    """Install SKILL.md to ~/.claude/skills/session-index/.

    Args:
        target_dir: install location (default ~/.claude/skills/session-index)
        copy: True for a static copy (snapshot, supply-chain-safe).
              False for a symlink (live updates when the package changes).
        force: overwrite an existing SKILL.md.

    Returns True on success, False on no-op (already installed without force).
    """
    target_dir = Path(target_dir).expanduser() if target_dir else DEFAULT_SKILL_TARGET

    if not SKILL_SOURCE.exists():
        print(
            f"error: skill source not found at {SKILL_SOURCE}.\n"
            "If you installed via PyPI or git URL, the package data may not have "
            "been shipped correctly. Try `uv tool install --reinstall` or install "
            "from a clone with `pip install -e .`.",
            file=sys.stderr,
        )
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "SKILL.md"

    if target_file.exists() or target_file.is_symlink():
        if not force:
            print(
                f"SKILL already installed at {target_file}.\n"
                "Use --force to overwrite."
            )
            return False
        target_file.unlink()

    if copy:
        target_file.write_text(SKILL_SOURCE.read_text())
        method = "copied"
    else:
        target_file.symlink_to(SKILL_SOURCE)
        method = "symlinked"

    print(f"SKILL {method} to {target_file}")
    return True


# ---------------------------------------------------------------------------
# configure-permissions
# ---------------------------------------------------------------------------

DEFAULT_CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"


def _cache_write_permission_pattern() -> str:
    """The Write() permission pattern that allows our cache writes."""
    cache_dir = Path(config.DEFAULTS["db_path"]).parent
    return f"Write({cache_dir}/**)"


def configure_permissions(
    settings_path: Path = None,
    dry_run: bool = False,
    remove: bool = False,
) -> bool:
    """Add or remove a write rule for our cache dir in ~/.claude/settings.json.

    The Claude Code sandbox blocks writes outside the project working
    directory by default. Without this rule, WAL mode falls back and the
    DB chmod-after-connect is the only way the index works inside a
    sandboxed agent loop. Adding the rule lets WAL run normally.

    Args:
        settings_path: override (default ~/.claude/settings.json)
        dry_run: print the change without writing
        remove: remove our rule instead of adding it

    Returns True if a change was made (or would be made in dry-run).
    """
    settings_path = (
        Path(settings_path).expanduser() if settings_path else DEFAULT_CLAUDE_SETTINGS
    )

    pattern = _cache_write_permission_pattern()

    # Load existing settings (or start empty)
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError as e:
            print(f"error: cannot parse {settings_path}: {e}", file=sys.stderr)
            return False
    else:
        settings = {}

    permissions = settings.setdefault("permissions", {})
    allow = permissions.setdefault("allow", [])

    if remove:
        if pattern not in allow:
            print(f"Permission not present, nothing to remove: {pattern}")
            return False
        if dry_run:
            print(f"Would remove from {settings_path}:\n  {pattern}")
            return True
        allow.remove(pattern)
        action = "Removed"
        preposition = "from"
    else:
        if pattern in allow:
            print(f"Permission already present: {pattern}")
            return False
        if dry_run:
            print(f"Would add to {settings_path}:\n  {pattern}")
            return True
        allow.append(pattern)
        action = "Added"
        preposition = "to"

    # Backup before writing if the file existed
    if settings_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = settings_path.with_name(f"{settings_path.name}.bak.{timestamp}")
        backup.write_bytes(settings_path.read_bytes())
        print(f"  backup: {backup}")

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print(f"{action} {pattern} {preposition} {settings_path}")
    return True


# ---------------------------------------------------------------------------
# init-config
# ---------------------------------------------------------------------------

def init_config_cmd(force: bool = False) -> bool:
    """Write a default config file. Wraps config.init_config with --force."""
    if config.CONFIG_FILE.exists() and not force:
        print(
            f"Config already exists at {config.CONFIG_FILE}.\n"
            "Use --force to overwrite."
        )
        return False

    if config.CONFIG_FILE.exists():
        config.CONFIG_FILE.unlink()

    if config.init_config():
        print(f"Wrote default config to {config.CONFIG_FILE}")
        return True
    return False
