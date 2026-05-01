#!/usr/bin/env python3
"""One-time setup: tell git to load hooks from scripts/git-hooks/ in this clone.

Why a separate hooks directory:
  Git's default hook location is .git/hooks/, which is local to each clone
  and never tracked. To keep our hooks reproducible and in version control,
  we point git at scripts/git-hooks/ via core.hooksPath. That way the hooks
  travel with the repo and anyone who clones the project can opt in by
  running this script once.

Run this immediately after cloning:

    python scripts/install-hooks.py

Idempotent — re-running just re-applies the config.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ROOT / "scripts" / "git-hooks"


def main() -> int:
    if not HOOKS_DIR.is_dir():
        print(f"error: hooks directory not found: {HOOKS_DIR}", file=sys.stderr)
        return 1

    rel = HOOKS_DIR.relative_to(ROOT)
    proc = subprocess.run(
        ["git", "config", "core.hooksPath", str(rel)],
        cwd=ROOT,
    )
    if proc.returncode != 0:
        print("error: `git config core.hooksPath` failed", file=sys.stderr)
        return proc.returncode

    print(f"ok: git is now using hooks from {rel}/")
    print("    pre-push will run scripts/preflight.py before each push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
