"""Sanitize / validate recon job_id strings (copy-paste whitespace resilience)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HEX12 = re.compile(r"^[0-9a-fA-F]{12}$")


def sanitize_job_id(
    job_id: str,
    *,
    warn: bool = True,
    stream=None,
) -> str:
    """Remove whitespace/newlines from job_id; warn if changed or non-12-hex.

    Does not hard-fail on format — callers still fail if the folder is missing.
    Generation remains uuid4().hex[:12]; this only cleans pasted CLI/API input.
    """
    original = job_id if isinstance(job_id, str) else str(job_id)
    cleaned = (
        original.replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace("\t", "")
        .strip()
    )
    out = stream if stream is not None else sys.stderr
    if warn and cleaned != original:
        print(
            f"Warning: job_id sanitized from {original!r} to {cleaned!r}",
            file=out,
        )
    if warn and cleaned and not _HEX12.match(cleaned):
        print(
            f"Warning: job_id {cleaned!r} may be invalid (expected 12 hex chars)",
            file=out,
        )
    return cleaned


def join_job_id_tokens(tokens: list[str] | tuple[str, ...] | str | None) -> str | None:
    """Join argparse nargs='+' tokens (or pass-through str) then sanitize."""
    if tokens is None:
        return None
    if isinstance(tokens, str):
        raw = tokens
    else:
        raw = "".join(str(t) for t in tokens)
    if not raw:
        return None
    return sanitize_job_id(raw)


def sanitize_job_dir(job_dir: Path, *, warn: bool = True) -> Path:
    """If the leaf folder name has whitespace, rebuild path with sanitized leaf."""
    leaf = job_dir.name
    cleaned = sanitize_job_id(leaf, warn=warn)
    if cleaned == leaf:
        return job_dir
    return job_dir.parent / cleaned
