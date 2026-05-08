"""Drift check: package __version__ must match pyproject.toml's project.version."""

import tomllib
import unittest
from pathlib import Path

from session_index import __version__ as package_version


class VersionConsistencyTests(unittest.TestCase):
    def test_pyproject_version_matches_dunder_version(self):
        repo_root = Path(__file__).resolve().parent.parent
        with open(repo_root / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        self.assertEqual(
            data["project"]["version"],
            package_version,
            "version drift between pyproject.toml and session_index.__version__ — "
            "bump both to the same value",
        )


if __name__ == "__main__":
    unittest.main()
