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
                Path("/tmp/cfg/claude-session-index/config.json"),
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
        cfg_path = self.tmp / "cfg" / "config.json"
        with mock.patch.object(self.config, "CONFIG_FILE", cfg_path):
            ok = self.config.init_config()
        self.assertTrue(ok)
        self.assertTrue(cfg_path.exists())
        self.assertEqual(self._mode(cfg_path), 0o600)
        self.assertEqual(self._mode(cfg_path.parent), 0o700)


if __name__ == "__main__":
    unittest.main()
