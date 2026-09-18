"""Test P1-12: Token hash-only storage and session management.

Verifies that JWT tokens are replaced with session-based tokens
where only SHA-256 hashes are stored in memory.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from api.auth import _make_token, _invalidate_token, _active_tokens, _validate_session_token
import hashlib
import time


class TestTokenHashStorage(unittest.TestCase):
    """Test that tokens are stored as hashes only."""

    def setUp(self):
        """Clear active tokens before each test."""
        _active_tokens.clear()

    def tearDown(self):
        """Clear active tokens after each test."""
        _active_tokens.clear()

    def test_make_token_returns_tuple(self):
        """_make_token should return (plain_token, token_hash) tuple."""
        plain, hashed = _make_token("operator", "operator")
        self.assertIsInstance(plain, str)
        self.assertIsInstance(hashed, str)
        self.assertEqual(len(plain), 64)  # 32 bytes = 64 hex chars
        self.assertEqual(len(hashed), 64)  # SHA-256 = 64 hex chars

    def test_token_hash_matches_sha256(self):
        """Stored hash should match SHA-256 of plain token."""
        plain, expected_hash = _make_token("operator", "operator")
        actual_hash = hashlib.sha256(plain.encode()).hexdigest()
        self.assertEqual(actual_hash, expected_hash)

    def test_token_stored_in_memory(self):
        """Token hash should be stored in _active_tokens."""
        plain, _ = _make_token("operator", "operator")
        token_hash = hashlib.sha256(plain.encode()).hexdigest()
        self.assertIn(token_hash, _active_tokens)

    def test_token_metadata_stored(self):
        """Token metadata (role, exp, username) should be stored."""
        plain, _ = _make_token("engineer", "engineer_user")
        token_hash = hashlib.sha256(plain.encode()).hexdigest()
        session = _active_tokens[token_hash]
        self.assertEqual(session["role"], "engineer")
        self.assertEqual(session["username"], "engineer_user")
        self.assertGreater(session["exp"], time.time())

    def test_invalidate_token_removes_from_store(self):
        """_invalidate_token should remove token from _active_tokens."""
        plain, _ = _make_token("operator", "operator")
        token_hash = hashlib.sha256(plain.encode()).hexdigest()
        self.assertIn(token_hash, _active_tokens)
        
        _invalidate_token(plain)
        self.assertNotIn(token_hash, _active_tokens)

    def test_invalidate_nonexistent_token_no_error(self):
        """Invalidating non-existent token should not raise."""
        fake_token = "a" * 64
        _invalidate_token(fake_token)  # Should not raise

    def test_different_tokens_have_different_hashes(self):
        """Two different tokens should have different hashes."""
        plain1, _ = _make_token("operator", "operator")
        plain2, _ = _make_token("operator", "operator")
        hash1 = hashlib.sha256(plain1.encode()).hexdigest()
        hash2 = hashlib.sha256(plain2.encode()).hexdigest()
        self.assertNotEqual(hash1, hash2)

    def test_no_plain_tokens_in_memory(self):
        """Plain tokens should NOT be keys in _active_tokens."""
        plain, _ = _make_token("operator", "operator")
        # Keys should be hashes, not plain tokens
        for key in _active_tokens:
            self.assertNotEqual(key, plain)
            self.assertEqual(len(key), 64)  # Hash length

    def test_token_expiration_check(self):
        """Token should have expiration time set."""
        plain, _ = _make_token("operator", "operator")
        token_hash = hashlib.sha256(plain.encode()).hexdigest()
        session = _active_tokens[token_hash]
        # Expiration should be ~TOKEN_TTL_SEC (28800s = 8h) in the future
        self.assertGreater(session["exp"], time.time() + 28000)


class TestTokenUniqueness(unittest.TestCase):
    """Test that tokens are cryptographically random."""

    def setUp(self):
        _active_tokens.clear()

    def tearDown(self):
        _active_tokens.clear()

    def test_tokens_are_unique(self):
        """Generated tokens should be unique (not collide)."""
        tokens = set()
        for _ in range(100):
            plain, _ = _make_token("operator", "operator")
            tokens.add(plain)
        # All 100 tokens should be unique
        self.assertEqual(len(tokens), 100)


if __name__ == "__main__":
    unittest.main()
