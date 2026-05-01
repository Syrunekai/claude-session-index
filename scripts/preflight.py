#!/usr/bin/env python3
"""Pre-push preflight checks. Runs everything that should be green before publishing.

Checks (in order):
  1. skills/session-index/SKILL.md is in sync with session_index/_skill/SKILL.md
  2. config.example.toml is in sync with session_index/config.py:CONFIG_TEMPLATE
  3. The test suite passes

Exit code 0 means safe to push; non-zero means abort.

Invoke directly:
    python scripts/preflight.py

Or wired into git's pre-push hook automatically — see scripts/install-hooks.py.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(label: str, cmd: list) -> bool:
    """Run cmd in repo root, return True on success, False on failure."""
    print(f"=== {label} ===", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        print(f"FAIL: {label}\n", file=sys.stderr)
        return False
    return True


def main() -> int:
    checks = [
        ("skill sync check",
         [sys.executable, "scripts/sync-skill.py", "--check"]),
        ("config example sync check",
         [sys.executable, "scripts/sync-config-example.py", "--check"]),
        ("test suite",
         [sys.executable, "-m", "unittest", "discover", "-s", "tests"]),
    ]

    failures = sum(0 if run(label, cmd) else 1 for label, cmd in checks)

    if failures == 0:
        print("=== ALL GREEN — safe to push ===")
        return 0

    print(f"=== {failures} CHECK(S) FAILED — push aborted ===", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
