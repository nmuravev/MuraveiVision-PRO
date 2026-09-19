"""Unit tests for safe_bool / safe_int (config_utils)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.config_utils import safe_bool, safe_int


class SafeBoolTests(unittest.TestCase):
    """Tests for safe_bool with various input types."""

    def test_true_values(self):
        """Truthy values should return True."""
        self.assertTrue(safe_bool('True'))
        self.assertTrue(safe_bool('true'))
        self.assertTrue(safe_bool('1'))
        self.assertTrue(safe_bool('yes'))
        self.assertTrue(safe_bool(1))
        self.assertTrue(safe_bool(True))
        self.assertTrue(safe_bool(1.0))

    def test_false_values(self):
        """Falsy values should return False."""
        self.assertFalse(safe_bool('False'))
        self.assertFalse(safe_bool('false'))
        self.assertFalse(safe_bool('0'))
        self.assertFalse(safe_bool('no'))
        self.assertFalse(safe_bool(0))
        self.assertFalse(safe_bool(False))
        self.assertFalse(safe_bool(0.0))

    def test_default_values(self):
        """Unparseable values should return default (False)."""
        self.assertFalse(safe_bool(None))
        self.assertFalse(safe_bool('junk'))
        self.assertFalse(safe_bool(''))
        self.assertFalse(safe_bool('random'))

    def test_custom_default(self):
        """Custom default should be used for unparseable values."""
        self.assertTrue(safe_bool(None, True))
        self.assertTrue(safe_bool('junk', True))
        self.assertFalse(safe_bool(None, False))


class SafeIntTests(unittest.TestCase):
    """Tests for safe_int with various input types."""

    def test_valid_values(self):
        """Valid values should parse correctly."""
        self.assertEqual(safe_int('8001'), 8001)
        self.assertEqual(safe_int('42'), 42)
        self.assertEqual(safe_int(42), 42)
        self.assertEqual(safe_int(0), 0)
        self.assertEqual(safe_int('-10'), -10)
        self.assertEqual(safe_int(-5), -5)

    def test_default_values(self):
        """Invalid values should return default (0)."""
        self.assertEqual(safe_int('NaN'), 0)
        self.assertEqual(safe_int(None), 0)
        self.assertEqual(safe_int('junk'), 0)
        self.assertEqual(safe_int(''), 0)

    def test_custom_default(self):
        """Custom default should be used for invalid values."""
        self.assertEqual(safe_int('junk', 99), 99)
        self.assertEqual(safe_int(None, -1), -1)
        self.assertEqual(safe_int('NaN', 42), 42)


if __name__ == '__main__':
    unittest.main()
