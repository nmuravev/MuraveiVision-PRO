# KEEP: session trace — do not remove without explicit user order
"""Trace-Id extraction + toggle for session trace middleware."""
from __future__ import annotations

import unittest

from services import trace_middleware as tm


class TraceMiddlewareHelpersTests(unittest.TestCase):
    def test_extract_trace_id_from_headers(self) -> None:
        headers = [
            (b"host", b"127.0.0.1"),
            (b"x-muravei-trace-id", b"abc-42"),
        ]
        self.assertEqual(tm.extract_trace_id(headers), "abc-42")

    def test_extract_trace_id_mints_when_missing(self) -> None:
        tid = tm.extract_trace_id([(b"host", b"127.0.0.1")])
        self.assertTrue(tid.startswith("be-"))

    def test_toggle_enabled(self) -> None:
        prev = tm.is_trace_enabled()
        try:
            tm.set_trace_enabled(False)
            self.assertFalse(tm.is_trace_enabled())
            tm.set_trace_enabled(True)
            self.assertTrue(tm.is_trace_enabled())
        finally:
            tm.set_trace_enabled(prev)


if __name__ == "__main__":
    unittest.main()
