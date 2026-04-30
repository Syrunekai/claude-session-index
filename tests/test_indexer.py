"""Tests for session_index.indexer — WAL fallback and DB perm hardening."""

import importlib
import io
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class WalFallbackTests(unittest.TestCase):
    """Section A: WAL pragma try/except + once-per-invocation warning."""

    def setUp(self):
        from session_index import indexer
        importlib.reload(indexer)
        self.indexer_module = indexer
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-wal-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wal_succeeds_normally_no_warning(self):
        """Happy path: WAL works in a writable dir, no fallback warning."""
        db = self.tmp / "ok.db"
        idx = self.indexer_module.SessionIndexer(db_path=db, projects_dir=self.tmp)
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            idx.connect()
            idx.close()
        # Other Python warnings can land in stderr; we only care that ours did not.
        self.assertNotIn("WAL", buf.getvalue())
        # And WAL really is the active mode
        conn = sqlite3.connect(str(db))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        self.assertEqual(mode.lower(), "wal")

    def test_emit_wal_warning_writes_to_stderr(self):
        """Direct unit test of the warning emitter."""
        # Reset the module-level flag so the test is deterministic
        self.indexer_module._wal_warning_emitted = False
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            self.indexer_module._emit_wal_fallback_warning()
        out = buf.getvalue()
        self.assertIn("WAL", out)
        self.assertIn("warning", out.lower())

    def test_emit_wal_warning_only_once_per_process(self):
        """Repeated calls to the emitter only print on the first call."""
        self.indexer_module._wal_warning_emitted = False
        buf = io.StringIO()
        with mock.patch.object(sys, "stderr", buf):
            self.indexer_module._emit_wal_fallback_warning()
            self.indexer_module._emit_wal_fallback_warning()
            self.indexer_module._emit_wal_fallback_warning()
        # All three calls, only one warning printed
        self.assertEqual(buf.getvalue().lower().count("warning"), 1)


class DbPermissionTests(unittest.TestCase):
    """Section C: DB file gets 0o600 after connect."""

    def setUp(self):
        from session_index import indexer
        self.indexer_module = indexer
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-dbperm-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_db_file_chmod_after_connect(self):
        db = self.tmp / "secured.db"
        idx = self.indexer_module.SessionIndexer(db_path=db, projects_dir=self.tmp)
        idx.connect()
        idx.close()
        self.assertEqual(stat.S_IMODE(db.stat().st_mode), 0o600)

    def test_db_file_heals_loose_perms(self):
        """Existing DB with 0o644 perms gets healed to 0o600 on next connect."""
        db = self.tmp / "loose.db"
        # Create the file out-of-band with loose perms
        db.write_bytes(b"")
        db.chmod(0o644)
        idx = self.indexer_module.SessionIndexer(db_path=db, projects_dir=self.tmp)
        idx.connect()
        idx.close()
        self.assertEqual(stat.S_IMODE(db.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
