# Documentation Sync Checklist

Use this after every code change to ensure docs stay in sync.

## Pre-Commit Checklist

- [ ] All tests pass (unit + E2E when UI changed + `tsc --noEmit`)
- [ ] `docs/ROADMAP.md` updated (DONE section with commit hash)
- [ ] `docs/TODO.md` updated (checklists reflect current state)
- [ ] `docs/API.md` updated (if endpoints changed)
- [ ] `docs/FEATURES.md` updated (if features added)
- [ ] `docs/ARCHITECTURE.md` updated (if invariants changed)
- [ ] `docs/KNOWN_ISSUES.md` updated (if new limitations)
- [ ] `docs/MASTER_PLAN.md` Meta section updated (date, commit, test count, status)
- [ ] `docs/ANALYST_GUIDE.md` updated (if UI workflow changed)
- [ ] `docs/ENGINEER_GUIDE.md` updated (if deployment changed)
- [ ] `docs/ERROR_REFERENCE.md` updated (if error codes added)

## Quick Reference

| Change Type | Docs to Update |
|-------------|----------------|
| New API endpoint | API.md, FEATURES.md, MASTER_PLAN.md |
| UI change | ANALYST_GUIDE.md, FEATURES.md |
| Architecture change | ARCHITECTURE.md, MASTER_PLAN.md |
| New error code | ERROR_REFERENCE.md |
| Deployment change | ENGINEER_GUIDE.md |
| Bug fix | KNOWN_ISSUES.md (remove if fixed) |
| Sprint complete | ROADMAP.md, TODO.md, MASTER_PLAN.md |

## Automation

Cursor follows [`.cursorrules`](../.cursorrules) to auto-update docs after every change.
This checklist is for manual verification or when Cursor is not used.

## Related

- Master overview: [`MASTER_PLAN.md`](MASTER_PLAN.md)
- Agent entry: [`../AGENTS.md`](../AGENTS.md)
