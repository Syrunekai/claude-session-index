"""Tests for session_index.installer — install-skill, configure-permissions, init-config."""

import importlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class InstallSkillTests(unittest.TestCase):
    def setUp(self):
        from session_index import installer
        self.installer = installer
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-skill-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_copy_creates_static_file(self):
        target = self.tmp / "skills" / "session-index"
        ok = self.installer.install_skill(target_dir=target, copy=True)
        self.assertTrue(ok)
        skill_file = target / "SKILL.md"
        self.assertTrue(skill_file.exists())
        self.assertFalse(skill_file.is_symlink())
        # Content should match the package source
        self.assertEqual(skill_file.read_text(), self.installer.SKILL_SOURCE.read_text())

    def test_link_creates_symlink_to_source(self):
        target = self.tmp / "skills" / "session-index"
        ok = self.installer.install_skill(target_dir=target, copy=False)
        self.assertTrue(ok)
        skill_file = target / "SKILL.md"
        self.assertTrue(skill_file.is_symlink())
        self.assertEqual(
            skill_file.resolve(),
            self.installer.SKILL_SOURCE.resolve(),
        )

    def test_no_overwrite_without_force(self):
        target = self.tmp / "skills" / "session-index"
        target.mkdir(parents=True)
        existing = target / "SKILL.md"
        existing.write_text("preexisting content")
        ok = self.installer.install_skill(target_dir=target, copy=True, force=False)
        self.assertFalse(ok)
        self.assertEqual(existing.read_text(), "preexisting content")

    def test_force_overwrites(self):
        target = self.tmp / "skills" / "session-index"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("preexisting content")
        ok = self.installer.install_skill(target_dir=target, copy=True, force=True)
        self.assertTrue(ok)
        self.assertEqual(
            (target / "SKILL.md").read_text(),
            self.installer.SKILL_SOURCE.read_text(),
        )

    def test_force_replaces_symlink_with_copy(self):
        """If switching from --link to default copy, force replaces the symlink."""
        target = self.tmp / "skills" / "session-index"
        self.installer.install_skill(target_dir=target, copy=False)
        self.assertTrue((target / "SKILL.md").is_symlink())
        ok = self.installer.install_skill(target_dir=target, copy=True, force=True)
        self.assertTrue(ok)
        self.assertFalse((target / "SKILL.md").is_symlink())


class ConfigurePermissionsTests(unittest.TestCase):
    def setUp(self):
        from session_index import installer
        importlib.reload(installer)
        self.installer = installer
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-perms-"))
        self.settings = self.tmp / "settings.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_adds_to_empty_settings(self):
        ok = self.installer.configure_permissions(settings_path=self.settings)
        self.assertTrue(ok)
        data = json.loads(self.settings.read_text())
        pattern = self.installer._cache_write_permission_pattern()
        self.assertIn(pattern, data["permissions"]["allow"])

    def test_preserves_existing_keys(self):
        self.settings.write_text(json.dumps({
            "permissions": {"allow": ["Bash(ls:*)"]},
            "model": "opus",
        }))
        self.installer.configure_permissions(settings_path=self.settings)
        data = json.loads(self.settings.read_text())
        self.assertIn("Bash(ls:*)", data["permissions"]["allow"])
        self.assertEqual(data.get("model"), "opus")

    def test_idempotent_on_second_run(self):
        self.installer.configure_permissions(settings_path=self.settings)
        # Second run should be no-op
        ok = self.installer.configure_permissions(settings_path=self.settings)
        self.assertFalse(ok)
        data = json.loads(self.settings.read_text())
        pattern = self.installer._cache_write_permission_pattern()
        # Only one entry
        self.assertEqual(data["permissions"]["allow"].count(pattern), 1)

    def test_dry_run_does_not_write(self):
        ok = self.installer.configure_permissions(
            settings_path=self.settings, dry_run=True,
        )
        self.assertTrue(ok)
        # File was not created
        self.assertFalse(self.settings.exists())

    def test_remove_takes_out_our_entry(self):
        self.installer.configure_permissions(settings_path=self.settings)
        ok = self.installer.configure_permissions(
            settings_path=self.settings, remove=True,
        )
        self.assertTrue(ok)
        data = json.loads(self.settings.read_text())
        pattern = self.installer._cache_write_permission_pattern()
        self.assertNotIn(pattern, data["permissions"]["allow"])

    def test_remove_is_noop_when_not_present(self):
        self.settings.write_text(json.dumps({"permissions": {"allow": []}}))
        ok = self.installer.configure_permissions(
            settings_path=self.settings, remove=True,
        )
        self.assertFalse(ok)

    def test_invalid_json_returns_false(self):
        self.settings.write_text("{ this is not json")
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            ok = self.installer.configure_permissions(settings_path=self.settings)
        self.assertFalse(ok)
        self.assertIn("cannot parse", buf.getvalue())

    def test_creates_backup_before_writing(self):
        self.settings.write_text(json.dumps({"permissions": {"allow": []}}))
        self.installer.configure_permissions(settings_path=self.settings)
        # A backup file should exist alongside the settings
        backups = list(self.tmp.glob("settings.json.bak.*"))
        self.assertEqual(len(backups), 1)


class InitConfigCmdTests(unittest.TestCase):
    def setUp(self):
        from session_index import installer, config
        self.installer = installer
        self.config = config
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-initcfg-"))
        # Redirect CONFIG_FILE for the test
        self.cfg_path = self.tmp / "config.json"
        self._patch = mock.patch.object(self.config, "CONFIG_FILE", self.cfg_path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writes_default_when_missing(self):
        ok = self.installer.init_config_cmd()
        self.assertTrue(ok)
        self.assertTrue(self.cfg_path.exists())
        self.assertEqual(stat.S_IMODE(self.cfg_path.stat().st_mode), 0o600)

    def test_no_overwrite_without_force(self):
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg_path.write_text("{}")
        ok = self.installer.init_config_cmd(force=False)
        self.assertFalse(ok)
        self.assertEqual(self.cfg_path.read_text(), "{}")

    def test_force_overwrites(self):
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg_path.write_text("{}")
        ok = self.installer.init_config_cmd(force=True)
        self.assertTrue(ok)
        # File should now contain default config (more than just empty object)
        self.assertGreater(len(self.cfg_path.read_text()), 5)


if __name__ == "__main__":
    unittest.main()
