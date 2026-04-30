"""Tests for session_index.config — path resolution, legacy notice, perms."""

import importlib
import io
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _reload_config():
    """Re-import the config module so module-level state (DEFAULTS, flags) is fresh."""
    from session_index import config
    importlib.reload(config)
    return config


class XDGPathResolutionTests(unittest.TestCase):
    """Section B: XDG-compliant default paths and env var overrides."""

    def test_xdg_cache_home_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_CACHE_HOME", None)
            config = _reload_config()
            self.assertEqual(config._xdg_cache_home(), Path.home() / ".cache")

    def test_xdg_cache_home_env_override(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/custom-cache"}):
            config = _reload_config()
            self.assertEqual(config._xdg_cache_home(), Path("/tmp/custom-cache"))

    def test_xdg_config_home_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_CONFIG_HOME", None)
            config = _reload_config()
            self.assertEqual(config._xdg_config_home(), Path.home() / ".config")

    def test_xdg_config_home_env_override(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/custom-config"}):
            config = _reload_config()
            self.assertEqual(config._xdg_config_home(), Path("/tmp/custom-config"))

    def test_default_db_path_under_xdg_cache(self):
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/c"}):
            config = _reload_config()
            self.assertEqual(
                config.DEFAULTS["db_path"],
                "/tmp/c/claude-session-index/sessions.db",
            )

    def test_default_config_file_under_xdg_config(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/cfg"}):
            config = _reload_config()
            self.assertEqual(
                config.CONFIG_FILE,
                Path("/tmp/cfg/claude-session-index/config.toml"),
            )

    def test_topics_dir_unchanged(self):
        """Topics live under ~/.claude/, not in our XDG namespace."""
        config = _reload_config()
        self.assertEqual(
            config.DEFAULTS["topics_dir"],
            str(Path.home() / ".claude" / "session-topics"),
        )


class LegacyNoticeTests(unittest.TestCase):
    """Section B: ~/.session-index/ legacy detection."""

    def setUp(self):
        self.tmp_home = Path(tempfile.mkdtemp(prefix="csi-home-"))
        self.legacy_dir = self.tmp_home / ".session-index"
        self._home_patch = mock.patch.object(Path, "home", lambda: self.tmp_home)
        self._home_patch.start()
        self.config = _reload_config()
        self.config._legacy_notice_emitted = False

    def tearDown(self):
        self._home_patch.stop()
        shutil.rmtree(self.tmp_home, ignore_errors=True)

    def _capture_stderr(self, fn):
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            fn()
        return buf.getvalue()

    def test_silent_when_no_legacy(self):
        out = self._capture_stderr(self.config._maybe_emit_legacy_path_notice)
        self.assertEqual(out, "")

    def test_emits_when_legacy_db_exists(self):
        self.legacy_dir.mkdir(parents=True)
        (self.legacy_dir / "sessions.db").write_text("x")
        out = self._capture_stderr(self.config._maybe_emit_legacy_path_notice)
        self.assertIn("legacy", out)
        self.assertIn("sessions.db", out)

    def test_emits_when_legacy_config_exists(self):
        self.legacy_dir.mkdir(parents=True)
        (self.legacy_dir / "config.json").write_text("{}")
        out = self._capture_stderr(self.config._maybe_emit_legacy_path_notice)
        self.assertIn("config.json", out)

    def test_only_emits_once(self):
        self.legacy_dir.mkdir(parents=True)
        (self.legacy_dir / "sessions.db").write_text("x")
        first = self._capture_stderr(self.config._maybe_emit_legacy_path_notice)
        second = self._capture_stderr(self.config._maybe_emit_legacy_path_notice)
        self.assertNotEqual(first, "")
        self.assertEqual(second, "")


class SecurePermissionTests(unittest.TestCase):
    """Section C: secure_mkdir and secure_chmod_file."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-perm-"))
        from session_index import config
        self.config = config

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _mode(self, path):
        return stat.S_IMODE(path.stat().st_mode)

    def test_mkdir_creates_with_mode(self):
        target = self.tmp / "fresh"
        self.config.secure_mkdir(target, 0o700)
        self.assertEqual(self._mode(target), 0o700)

    def test_mkdir_heals_existing(self):
        target = self.tmp / "loose"
        target.mkdir(mode=0o755)
        self.config.secure_mkdir(target, 0o700)
        self.assertEqual(self._mode(target), 0o700)

    def test_mkdir_accepts_string(self):
        target = self.tmp / "from-str"
        self.config.secure_mkdir(str(target), 0o700)
        self.assertEqual(self._mode(target), 0o700)

    def test_chmod_file_heals(self):
        f = self.tmp / "loose.txt"
        f.write_text("x")
        f.chmod(0o644)
        self.config.secure_chmod_file(f, 0o600)
        self.assertEqual(self._mode(f), 0o600)

    def test_chmod_file_silent_when_missing(self):
        # No file at this path; should not raise.
        self.config.secure_chmod_file(self.tmp / "nonexistent.txt", 0o600)

    def test_get_db_path_creates_secure_parent(self):
        target = self.tmp / "csi" / "sessions.db"
        self.config.get_db_path(override=str(target))
        self.assertTrue(target.parent.exists())
        self.assertEqual(self._mode(target.parent), 0o700)

    def test_init_config_writes_secure_file(self):
        cfg_path = self.tmp / "cfg" / "config.toml"
        with mock.patch.object(self.config, "CONFIG_FILE", cfg_path):
            ok = self.config.init_config()
        self.assertTrue(ok)
        self.assertTrue(cfg_path.exists())
        self.assertEqual(self._mode(cfg_path), 0o600)
        self.assertEqual(self._mode(cfg_path.parent), 0o700)
        # Content must be valid TOML matching the template
        import tomllib
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
        self.assertEqual(
            data.get("schema_version"),
            self.config.CURRENT_SCHEMA_VERSION,
        )


class TomlLoadingTests(unittest.TestCase):
    """Section E: _load_config_file uses tomllib."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-toml-"))
        from session_index import config
        self.config = config

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_reads_valid_toml(self):
        cfg = self.tmp / "config.toml"
        cfg.write_text(
            'schema_version = 1\n'
            'projects_dir = "/tmp/projects"\n'
            'clients = ["Acme", "Beta"]\n'
        )
        with mock.patch.object(self.config, "CONFIG_FILE", cfg):
            data = self.config._load_config_file()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["projects_dir"], "/tmp/projects")
        self.assertEqual(data["clients"], ["Acme", "Beta"])

    def test_returns_empty_dict_on_invalid_toml(self):
        cfg = self.tmp / "config.toml"
        cfg.write_text("this is = not = valid toml\n")
        with mock.patch.object(self.config, "CONFIG_FILE", cfg):
            data = self.config._load_config_file()
        self.assertEqual(data, {})

    def test_returns_empty_dict_when_missing(self):
        cfg = self.tmp / "nonexistent.toml"
        with mock.patch.object(self.config, "CONFIG_FILE", cfg):
            data = self.config._load_config_file()
        self.assertEqual(data, {})


class SchemaVersionWarningTests(unittest.TestCase):
    """Section E: schema_version mismatch produces a one-time warning."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-schema-"))
        from session_index import config
        self.config = config
        self.config._schema_warning_emitted = False
        self.cfg = self.tmp / "config.toml"
        self._patch = mock.patch.object(self.config, "CONFIG_FILE", self.cfg)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _capture(self, fn):
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            fn()
        return buf.getvalue()

    def test_silent_when_no_config_file(self):
        # No file written; warning must not fire
        out = self._capture(lambda: self.config._maybe_emit_schema_warning({}))
        self.assertEqual(out, "")

    def test_silent_when_version_matches(self):
        self.cfg.write_text(f"schema_version = {self.config.CURRENT_SCHEMA_VERSION}\n")
        out = self._capture(lambda: self.config._maybe_emit_schema_warning(
            {"schema_version": self.config.CURRENT_SCHEMA_VERSION}
        ))
        self.assertEqual(out, "")

    def test_emits_when_version_missing(self):
        self.cfg.write_text("clients = []\n")  # file exists, no schema_version
        out = self._capture(lambda: self.config._maybe_emit_schema_warning({"clients": []}))
        self.assertIn("no schema_version", out)
        self.assertIn("config.example.toml", out)

    def test_emits_when_version_lower(self):
        self.cfg.write_text("schema_version = 0\n")
        out = self._capture(lambda: self.config._maybe_emit_schema_warning(
            {"schema_version": 0}
        ))
        self.assertIn("v0", out)
        self.assertIn(f"v{self.config.CURRENT_SCHEMA_VERSION}", out)

    def test_emits_when_version_higher(self):
        higher = self.config.CURRENT_SCHEMA_VERSION + 5
        self.cfg.write_text(f"schema_version = {higher}\n")
        out = self._capture(lambda: self.config._maybe_emit_schema_warning(
            {"schema_version": higher}
        ))
        self.assertIn(f"v{higher}", out)
        self.assertIn("not be recognized", out)

    def test_only_emits_once(self):
        self.cfg.write_text("schema_version = 0\n")
        first = self._capture(lambda: self.config._maybe_emit_schema_warning(
            {"schema_version": 0}
        ))
        second = self._capture(lambda: self.config._maybe_emit_schema_warning(
            {"schema_version": 0}
        ))
        self.assertNotEqual(first, "")
        self.assertEqual(second, "")


class GetConfigSchemaTests(unittest.TestCase):
    """Section E: get_config strips schema_version from runtime config."""

    def setUp(self):
        from session_index import config
        importlib.reload(config)
        self.config = config

    def test_schema_version_not_in_runtime_config(self):
        cfg_text = (
            'schema_version = 1\n'
            'projects_dir = "/custom/projects"\n'
        )
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False, mode="w") as f:
            f.write(cfg_text)
            cfg_path = Path(f.name)
        try:
            self.config._cached_config = None
            self.config._schema_warning_emitted = True  # suppress noise
            with mock.patch.object(self.config, "CONFIG_FILE", cfg_path):
                resolved = self.config.get_config()
            self.assertNotIn("schema_version", resolved)
            self.assertEqual(resolved["projects_dir"], "/custom/projects")
        finally:
            cfg_path.unlink()


class ConfigExampleSyncTests(unittest.TestCase):
    """Section E: config.example.toml at repo root tracks CONFIG_TEMPLATE."""

    def test_repo_example_in_sync_with_template(self):
        repo_root = Path(__file__).resolve().parent.parent
        derived = repo_root / "config.example.toml"
        self.assertTrue(derived.exists(),
                        f"derived config.example.toml missing at {derived}")
        from session_index.config import CONFIG_TEMPLATE
        self.assertEqual(
            derived.read_text(),
            CONFIG_TEMPLATE,
            "config.example.toml is out of sync with "
            "session_index/config.py:CONFIG_TEMPLATE.\n"
            "Run: python scripts/sync-config-example.py",
        )


if __name__ == "__main__":
    unittest.main()
