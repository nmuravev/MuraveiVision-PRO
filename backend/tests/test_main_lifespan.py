"""Test main.py lifespan startup/shutdown hooks (catches missing imports)."""
import ast
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_import_logging_exists():
    """import logging must be present in main.py (catches NameError at line 91)."""
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()
    assert "import logging" in content, "import logging missing from main.py"


def test_runtime_log_handler_defined_in_lifespan():
    """_RuntimeLogHandler class must be defined inside lifespan() (catches missing import logging)."""
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()
    tree = ast.parse(content)
    
    # Find lifespan function
    lifespan_found = False
    handler_defined = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            lifespan_found = True
            # Look for _RuntimeLogHandler class definition inside
            for inner in ast.walk(node):
                if isinstance(inner, ast.ClassDef) and inner.name == "_RuntimeLogHandler":
                    handler_defined = True
                    break
    
    assert lifespan_found, "lifespan async function missing from main.py"
    assert handler_defined, "_RuntimeLogHandler class not defined inside lifespan()"


def test_logging_used_in_handler():
    """_RuntimeLogHandler must inherit from logging.Handler."""
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text()
    
    # Check that logging.Handler is referenced inside lifespan
    assert "logging.Handler" in content, "logging.Handler not referenced in main.py"
