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


class MetadataTableTests(unittest.TestCase):
    """metadata table holds last_indexed_at as the freshness marker."""

    def setUp(self):
        from session_index import indexer
        self.indexer_module = indexer
        self.tmp = Path(tempfile.mkdtemp(prefix="csi-meta-"))
        # Empty projects dir is fine — backfill writes the timestamp regardless
        self.projects = self.tmp / "projects"
        self.projects.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_metadata_table_exists_after_connect(self):
        db = self.tmp / "meta.db"
        idx = self.indexer_module.SessionIndexer(db_path=db, projects_dir=self.projects)
        idx.connect()
        try:
            row = idx.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'"
            ).fetchone()
            self.assertIsNotNone(row)
        finally:
            idx.close()

    def test_get_last_indexed_at_none_before_first_run(self):
        db = self.tmp / "fresh.db"
        idx = self.indexer_module.SessionIndexer(db_path=db, projects_dir=self.projects)
        idx.connect()
        try:
            self.assertIsNone(idx.get_last_indexed_at())
        finally:
            idx.close()

    def test_backfill_writes_last_indexed_at(self):
        db = self.tmp / "backfill.db"
        idx = self.indexer_module.SessionIndexer(db_path=db, projects_dir=self.projects)
        idx.connect()
        try:
            import time
            before = int(time.time())
            idx.backfill_all()
            after = int(time.time())
            ts = idx.get_last_indexed_at()
            self.assertIsNotNone(ts)
            self.assertGreaterEqual(ts, before)
            self.assertLessEqual(ts, after)
        finally:
            idx.close()

    def test_index_incremental_writes_last_indexed_at(self):
        db = self.tmp / "incr.db"
        idx = self.indexer_module.SessionIndexer(db_path=db, projects_dir=self.projects)
        idx.connect()
        try:
            import time
            idx._record_indexed_at()  # seed an old value via direct call to test overwrite
            idx.conn.execute(
                "UPDATE metadata SET value=? WHERE key='last_indexed_at'",
                (str(int(time.time()) - 10000),),
            )
            idx.conn.commit()
            old_ts = idx.get_last_indexed_at()
            idx.index_incremental()
            new_ts = idx.get_last_indexed_at()
            self.assertGreater(new_ts, old_ts)
        finally:
            idx.close()


if __name__ == "__main__":
    unittest.main()
