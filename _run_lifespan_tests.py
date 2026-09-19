#!/usr/bin/env python3
"""Temporary test runner for lifespan tests."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

import unittest

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite = loader.discover('backend/tests', pattern='test_main_lifespan.py')
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
