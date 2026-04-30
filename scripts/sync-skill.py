#!/usr/bin/env python3
"""Sync the canonical SKILL.md into the conventional repo location.

The package ships SKILL.md inside session_index/_skill/ so `sessions
install-skill` can find it post-install. The conventional repo path
skills/session-index/SKILL.md must also exist as a real file (not a
symlink) so that `npx skills add` works on every OS — including
Windows, where git does not materialize symlinks by default.

Source of truth:  session_index/_skill/SKILL.md
Derived copy:     skills/session-index/SKILL.md

Edit the source. Run this script to refresh the derived file.

Usage:
    python scripts/sync-skill.py            # write derived from source
    python scripts/sync-skill.py --check    # exit non-zero if out of sync
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "session_index" / "_skill" / "SKILL.md"
DERIVED = ROOT / "skills" / "session-index" / "SKILL.md"


def main() -> int:
    check_mode = "--check" in sys.argv

    if not SOURCE.exists():
        print(f"error: source not found: {SOURCE}", file=sys.stderr)
        return 2

    source_text = SOURCE.read_text()

    if not DERIVED.exists():
        if check_mode:
            print(f"error: derived missing: {DERIVED}", file=sys.stderr)
            return 1
        DERIVED.parent.mkdir(parents=True, exist_ok=True)
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
            f"{SOURCE.relative_to(ROOT)}.\n"
            "Run: python scripts/sync-skill.py",
            file=sys.stderr,
        )
        return 1

    DERIVED.write_text(source_text)
    print(
        f"synced {SOURCE.relative_to(ROOT)} -> {DERIVED.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
