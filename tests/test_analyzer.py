"""Tests for session_index.analyzer.extract_exchanges — truncation, limit, direction."""

import json
import tempfile
import unittest
from pathlib import Path

from session_index.analyzer import extract_exchanges


def _write_session(path: Path, exchanges: list[tuple[str, str]]):
    """Write a synthetic Claude Code JSONL with the given (user, assistant) pairs.

    Each pair becomes one user line and one assistant line, in order. Timestamps
    are sequential so chronological order matches list order.
    """
    lines = []
    base_ts = "2026-05-07T12:00:"
    for i, (user_text, assistant_text) in enumerate(exchanges):
        lines.append(json.dumps({
            "type": "user",
            "message": {"content": [{"type": "text", "text": user_text}]},
            "timestamp": f"{base_ts}{i*2:02d}.000Z",
        }))
        lines.append(json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": assistant_text}]},
            "timestamp": f"{base_ts}{i*2+1:02d}.000Z",
        }))
    path.write_text("\n".join(lines) + "\n")


class TruncationTests(unittest.TestCase):
    """max_chars controls per-message truncation; None disables."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w")
        self.tmp.close()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_default_max_chars_truncates(self):
        _write_session(self.path, [("u" * 5000, "a" * 5000)])
        result = extract_exchanges(self.path)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["user"]), 1003)  # 1000 chars + "..."
        self.assertTrue(result[0]["user"].endswith("..."))
        self.assertTrue(result[0]["assistant"].endswith("..."))

    def test_max_chars_none_disables_truncation(self):
        _write_session(self.path, [("u" * 5000, "a" * 5000)])
        result = extract_exchanges(self.path, max_chars=None)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["user"]), 5000)
        self.assertEqual(len(result[0]["assistant"]), 5000)
        self.assertFalse(result[0]["user"].endswith("..."))

    def test_short_messages_unaffected_by_truncation(self):
        _write_session(self.path, [("hi", "hello")])
        result = extract_exchanges(self.path, max_chars=1000)
        self.assertEqual(result[0]["user"], "hi")
        self.assertEqual(result[0]["assistant"], "hello")


class LimitTests(unittest.TestCase):
    """limit controls exchange count; None returns all."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w")
        self.tmp.close()
        self.path = Path(self.tmp.name)
        # 25 exchanges so we can distinguish first/last/all
        _write_session(self.path, [(f"u{i}", f"a{i}") for i in range(25)])

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_default_limit_10(self):
        result = extract_exchanges(self.path)
        self.assertEqual(len(result), 10)

    def test_explicit_limit(self):
        result = extract_exchanges(self.path, limit=5)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["user"], "u0")
        self.assertEqual(result[-1]["user"], "u4")

    def test_limit_none_returns_all(self):
        result = extract_exchanges(self.path, limit=None)
        self.assertEqual(len(result), 25)

    def test_limit_exceeds_total(self):
        result = extract_exchanges(self.path, limit=100)
        self.assertEqual(len(result), 25)


class DirectionTests(unittest.TestCase):
    """from_end=True returns last N instead of first N."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w")
        self.tmp.close()
        self.path = Path(self.tmp.name)
        _write_session(self.path, [(f"u{i}", f"a{i}") for i in range(25)])

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_from_end_returns_last_exchanges(self):
        result = extract_exchanges(self.path, limit=5, from_end=True)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["user"], "u20")
        self.assertEqual(result[-1]["user"], "u24")

    def test_from_end_with_limit_none_returns_all(self):
        result = extract_exchanges(self.path, limit=None, from_end=True)
        self.assertEqual(len(result), 25)

    def test_from_end_default_false(self):
        # Sanity: from_end defaults to False — confirms back-compat
        result = extract_exchanges(self.path, limit=5)
        self.assertEqual(result[0]["user"], "u0")

    def test_from_end_limit_exceeds_total(self):
        result = extract_exchanges(self.path, limit=100, from_end=True)
        self.assertEqual(len(result), 25)


class CombinationTests(unittest.TestCase):
    """Verify CLI-equivalent flag combinations work end-to-end."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w")
        self.tmp.close()
        self.path = Path(self.tmp.name)
        # Long messages + many exchanges to stress both axes
        _write_session(self.path, [(f"u{i}" + "X" * 5000, f"a{i}" + "Y" * 5000)
                                    for i in range(25)])

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_full_flag_equivalent(self):
        # CLI: sessions context <id> --full
        result = extract_exchanges(self.path, limit=None, max_chars=None)
        self.assertEqual(len(result), 25)
        self.assertEqual(len(result[0]["user"]), 5002)  # u + 5000 X's + "0"... actually let me think

    def test_full_with_tail(self):
        # CLI: sessions context <id> --full --tail 3
        result = extract_exchanges(self.path, limit=3, max_chars=None, from_end=True)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["user"][:3], "u22")
        self.assertEqual(result[-1]["user"][:3], "u24")
        # No truncation
        self.assertGreater(len(result[0]["user"]), 1000)

    def test_full_with_head(self):
        # CLI: sessions context <id> --full -n 3
        result = extract_exchanges(self.path, limit=3, max_chars=None, from_end=False)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["user"][:2], "u0")

    def test_default_back_compat(self):
        # CLI: sessions context <id>  (no flags) — first 10, truncated
        result = extract_exchanges(self.path)
        self.assertEqual(len(result), 10)
        # All messages truncated
        for ex in result:
            self.assertTrue(ex["user"].endswith("..."))
            self.assertTrue(ex["assistant"].endswith("..."))


class QueryFilterTests(unittest.TestCase):
    """The query filter still works with the new flags."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w")
        self.tmp.close()
        self.path = Path(self.tmp.name)
        _write_session(self.path, [
            ("how do I use webhooks", "Webhooks are HTTP callbacks..."),
            ("unrelated topic about cats", "Cats are felines..."),
            ("more on webhooks signing", "HMAC verification ensures..."),
        ])

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_query_filters_to_matches(self):
        result = extract_exchanges(self.path, query="webhook")
        self.assertEqual(len(result), 2)

    def test_query_with_full_flag(self):
        # Filter still works alongside no-truncation/no-limit
        result = extract_exchanges(self.path, query="webhook",
                                   limit=None, max_chars=None)
        self.assertEqual(len(result), 2)

    def test_query_no_match_returns_empty(self):
        result = extract_exchanges(self.path, query="nonexistent_term_xyz")
        self.assertEqual(result, [])
