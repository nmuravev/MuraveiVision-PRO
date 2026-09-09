# Guidance for AI agents

This repository’s **source of truth** for project explanation is the [`docs/`](docs/README.md) folder.

Read in order:

1. [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md)  
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (часть B — инварианты агента)  
3. [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)  
4. [docs/MASTER_PLAN.md](docs/MASTER_PLAN.md) (статус / backlog / docs auto-sync)

After code changes: follow [`.cursorrules`](.cursorrules) and [docs/DOCS_SYNC_CHECKLIST.md](docs/DOCS_SYNC_CHECKLIST.md).

Do **not** treat `.backup/MuraveiVision/PROJECT_CONTEXT.md` or `.backup/.../ARCHITECTURE_FOR_AI.md` as current — they describe a superseded layout. [`docs/ARCHITECTURE_FOR_AI.md`](docs/ARCHITECTURE_FOR_AI.md) is a stub that points to [ARCHITECTURE.md](docs/ARCHITECTURE.md).

Python: only `muravei_env\Scripts\python.exe` (3.12.10). See `.cursor/rules/muravei-python-env.mdc`.

Agent skills: [docs/SKILL_CODEX.md](docs/SKILL_CODEX.md) (Codex/Astra) · [docs/SKILL_QWEN_LOCAL.md](docs/SKILL_QWEN_LOCAL.md) (local Qwen).
