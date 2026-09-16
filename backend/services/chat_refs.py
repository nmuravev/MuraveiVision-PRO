"""Parse detection:<id> tokens in network chat message bodies."""
from __future__ import annotations

import re

# 8–64 hex chars (matches typical detection UUIDs / 12-hex job-style ids)
DETECTION_REF_RE = re.compile(r"detection:([a-fA-F0-9]{8,64})\b")


def extract_detection_ids(body: str) -> list[str]:
    """Return unique detection ids in first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for m in DETECTION_REF_RE.finditer(body or ""):
        did = m.group(1).lower()
        if did not in seen:
            seen.add(did)
            out.append(did)
    return out


def format_detection_ref(det_id: str) -> str:
    return f"detection:{(det_id or '').strip().lower()}"
