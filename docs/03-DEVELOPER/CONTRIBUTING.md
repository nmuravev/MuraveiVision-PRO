# Contributing — MuraveiVision PRO

> **Git discipline, code review, air-gap constraints.**

## Overview

MuraveiVision PRO follows strict contribution guidelines to maintain code quality and security in air-gap environments.

## Git Discipline

### Branch Naming

```
feature/da3-backend
fix/websocket-reconnect
docs/api-reference
refactor/detection-service
test/add-unit-tests
chore/update-dependencies
```

### Commit Convention

**Format:** `type: subject`

```
feat: add DA3 dense backend
fix: resolve WebSocket reconnection issue
docs: update API reference with curl examples
refactor: simplify detection service logic
test: add unit tests for backup service
chore: update dependencies to latest versions
```

**Types:**
- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation only
- `refactor` — Code refactoring
- `test` — Adding/modifying tests
- `chore` — Maintenance tasks

### Commit Message Body

```
feat: add DA3 dense backend

- Add DA3 model wrapper for depth estimation
- Support DA3-S and DA3-B variants
- Add VRAM optimization for large models
- Update configuration schema

Fixes: #123
```

### Using .commit_msg.txt

```bash
# Create commit message file
echo "feat: add new detection model" > .commit_msg.txt
echo "" >> .commit_msg.txt
echo "Added support for YOLO26n model with improved" >> .commit_msg.txt
echo "performance on small object detection." >> .commit_msg.txt

# Commit using file
git add backend/models/yolo26.py
git commit -F .commit_msg.txt
```

## Pull Request Process

### PR Checklist

```
PR Checklist:
┌─────────────────────────────────────────┐
│  ☐ Tests pass (pytest backend/tests/ -q)│
│  ☐ TypeScript check (npx tsc --noEmit)  │
│  ☐ Python linting (ruff check)          │
│  ☐ TypeScript linting (eslint)          │
│  ☐ No debug code (print, console.log)  │
│  ☐ No hardcoded secrets                 │
│  ☐ Air-gap compatible                   │
│  ☐ Documentation updated                │
│  ☐ CHANGELOG.md updated                 │
│  ☐ Tests added for new code             │
│  ☐ Code follows style guidelines        │
└─────────────────────────────────────────┘
```

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Smoke tests pass
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Screenshots (if applicable)
Add screenshots of UI changes

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No new warnings
- [ ] Air-gap compatible
```

## Code Standards

### Python Standards

```bash
# Linting
ruff check backend/

# Formatting
ruff format backend/

# Type checking
mypy backend/ --ignore-missing-imports
```

**Rules:**
- Max line length: 88 characters (ruff default)
- Use type hints everywhere
- Docstrings for all public functions
- Async/await for I/O operations
- Exception handling with specific exceptions

### TypeScript Standards

```bash
# Type checking
npx tsc --noEmit

# Linting
npx eslint src/

# Formatting
npx prettier --check src/
```

**Rules:**
- Strict mode enabled
- No `any` types
- Interface for all object shapes
- Functional components only
- Custom hooks for reusable logic

## Air-Gap Constraints

### What's Allowed

```
✅ Vendored dependencies (in repo)
✅ Pre-downloaded models
✅ Offline git operations
✅ Local development
✅ Manual dependency transfer via USB
```

### What's NOT Allowed

```
❌ Runtime downloads from PyPI
❌ Runtime downloads from HuggingFace
❌ Runtime downloads from GitHub
❌ External API calls at runtime
❌ Auto-update mechanisms
❌ Telemetry or analytics
```

### Verifying Air-Gap Compliance

```python
# Check for forbidden imports
import ast
import sys

FORBIDDEN_DOMAINS = {
    "pypi.org",
    "huggingface.co",
    "github.com",
    "api.github.com"
}

def check_airgap_compliance(file_path):
    """Check if file contains network calls."""
    with open(file_path) as f:
        content = f.read()
    
    for domain in FORBIDDEN_DOMAINS:
        if domain in content:
            print(f"WARNING: Found {domain} in {file_path}")
            return False
    return True
```

## Code Review Guidelines

### Reviewer Checklist

```
Code Review Checklist:
┌─────────────────────────────────────────┐
│ Functionality:                          │
│ ☐ Code works as described              │
│ ☐ Edge cases handled                   │
│ ☐ Error handling appropriate           │
│ ☐ No performance regressions           │
│                                         │
│ Security:                               │
│ ☐ No hardcoded secrets                 │
│ ☐ Input validation present             │
│ ☐ SQL injection prevented              │
│ ☐ Path traversal prevented             │
│ ☐ Air-gap compliant                    │
│                                         │
│ Code Quality:                           │
│ ☐ Follows style guidelines             │
│ ☐ Functions are small and focused      │
│ ☐ Variables are well-named             │
│ ☐ Comments explain why, not what       │
│ ☐ No code duplication                  │
│                                         │
│ Testing:                                │
│ ☐ Tests added for new code             │
│ ☐ Tests are meaningful                 │
│ ☐ All tests pass                       │
│ ☐ Coverage maintained                  │
└─────────────────────────────────────────┘
```

### Review Process

```
1. Author creates PR
2. Automated checks run (CI)
3. Assign reviewer(s)
4. Reviewer leaves comments
5. Author addresses comments
6. Reviewer approves
7. Merge to main
```

## Adding New Features

### Step-by-Step

```bash
# 1. Create feature branch
git checkout -b feature/your-feature-name

# 2. Implement feature
# ... write code ...

# 3. Add tests
muravei_env\Scripts\python.exe -m pytest tests/ -v

# 4. Check code quality
ruff check backend/
mypy backend/
npx tsc --noEmit

# 5. Update documentation
# ... update docs ...

# 6. Commit
echo "feat: add your feature" > .commit_msg.txt
git add .
git commit -F .commit_msg.txt

# 7. Push and create PR
git push origin feature/your-feature-name
```

### Example: Adding New Model

```python
# backend/models/new_model.py
"""New model implementation."""

from typing import Any
import torch

class NewModel:
    """New model wrapper.
    
    Args:
        path: Path to model weights.
        device: Device to run on.
    """
    
    def __init__(self, path: str, device: str = "cuda"):
        self.path = path
        self.device = device
        self.model = self._load_model()
    
    def _load_model(self) -> Any:
        """Load model from path."""
        # Implementation here
        pass
    
    async def predict(self, image: bytes) -> dict:
        """Run inference on image.
        
        Args:
            image: Raw image bytes.
            
        Returns:
            Dictionary with predictions.
        """
        # Implementation here
        pass
```

## Bug Fixes

### Reporting Bugs

```markdown
Bug Report Template:

## Description
Clear description of the bug

## Steps to Reproduce
1. Step one
2. Step two
3. Step three

## Expected Behavior
What should happen

## Actual Behavior
What actually happens

## Environment
- OS: Windows 11
- Python: 3.11.9
- GPU: RTX 4070
- Version: v3.2.0

## Logs
```
Paste error logs here
```
```

### Fixing Bugs

```bash
# 1. Create fix branch
git checkout -b fix/issue-description

# 2. Fix the bug
# ... apply fix ...

# 3. Add regression test
# ... add test that catches the bug ...

# 4. Verify fix
muravei_env\Scripts\python.exe -m pytest tests/ -v

# 5. Commit and PR
echo "fix: resolve issue description" > .commit_msg.txt
git add .
git commit -F .commit_msg.txt
git push origin fix/issue-description
```

## Documentation Updates

### Updating Docs

```bash
# 1. Edit documentation files
# ... edit .md files in docs/ ...

# 2. Verify structure
# Check mkdocs.yml navigation

# 3. Commit
echo "docs: update documentation" > .commit_msg.txt
git add docs/
git commit -F .commit_msg.txt
```

### Docstring Format

```python
def detect_image(
    image: bytes,
    model: str,
    sahi_enabled: bool = False
) -> dict:
    """Detect objects in image.
    
    Args:
        image: Raw image bytes.
        model: Model name to use.
        sahi_enabled: Enable SAHI slicing.
        
    Returns:
        Dictionary with detections and metadata.
        
    Raises:
        ValueError: If image is invalid.
        RuntimeError: If model fails to load.
        
    Example:
        >>> result = detect_image(image_data, "yolo26s")
        >>> len(result["detections"])
        5
    """
```

## Release Process

### Creating Release

```bash
# 1. Update CHANGELOG.md
# ... add release notes ...

# 2. Tag release
git tag -a v3.2.0 -m "Release v3.2.0"

# 3. Push
git push origin main --tags

# 4. Create GitHub release
# ... via GitHub UI ...
```

## Getting Help

### Resources

- **Documentation:** [INDEX.md](../INDEX.md)
- **Issues:** GitHub Issues
- **Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
- **API:** [API_REFERENCE.md](./API_REFERENCE.md)

### Contact

- Open GitHub Issue for bugs
- Open GitHub PR for features
- Use conventional commits

## Версия

- **Приложение:** v3.2.0
- **Дата:** 2026-09-19
