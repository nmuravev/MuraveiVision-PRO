#!/usr/bin/env python3
"""Direct test runner — no discover()."""
import sys
import os

# Add repo root to path so 'backend' package is found
repo_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, repo_root)

import unittest

# Import the test module directly
from backend.tests import test_main_lifespan

def main():
    suite = unittest.TestSuite()
    suite.addTest(test_main_lifespan.test_lifespan_startup())
    suite.addTest(test_main_lifespan.test_lifespan_health_endpoint())
    suite.addTest(test_main_lifespan.test_runtime_log_handler_class_defined())
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    sys.exit(main())
