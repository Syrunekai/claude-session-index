#!/usr/bin/env python3
"""Sync config.example.toml at the repo root from the canonical CONFIG_TEMPLATE.

The template lives in session_index/config.py as a Python string constant.
This script regenerates the standalone reference file at the repo root so
that anyone browsing the repo on GitHub can see what the config looks like
without running the tool.

Usage:
    python scripts/sync-config-example.py            # write derived from source
    python scripts/sync-config-example.py --check    # exit non-zero if out of sync
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DERIVED = ROOT / "config.example.toml"

# Add the project to sys.path so we can import the template constant
sys.path.insert(0, str(ROOT))


def main() -> int:
    check_mode = "--check" in sys.argv

    from session_index.config import CONFIG_TEMPLATE
    source_text = CONFIG_TEMPLATE

    if not DERIVED.exists():
        if check_mode:
            print(f"error: derived missing: {DERIVED}", file=sys.stderr)
            return 1
        DERIVED.write_text(source_text)
        print(f"created {DERIVED.relative_to(ROOT)}")
        return 0

    derived_text = DERIVED.read_text()
    if source_text == derived_text:
        print(f"{DERIVED.relative_to(ROOT)}: already in sync")
        return 0

    if check_mode:
        print(
            f"error: {DERIVED.relative_to(ROOT)} is out of sync with "
            "session_index/config.py CONFIG_TEMPLATE.\n"
            "Run: python scripts/sync-config-example.py",
            file=sys.stderr,
        )
        return 1

    DERIVED.write_text(source_text)
    print(f"synced session_index/config.py:CONFIG_TEMPLATE -> {DERIVED.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
