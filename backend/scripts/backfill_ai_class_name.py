"""Optional one-shot: backfill detections.ai_class_name from class_name.

Startup migrate in services/db.py already runs the same UPDATE.
Use this script to re-apply on a portable DB without restarting the API.

  .\\muravei_env\\Scripts\\python.exe backend\\scripts\\backfill_ai_class_name.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
DB_PATH = BASE / "muravei.db"


def main() -> int:
    if not DB_PATH.is_file():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        return 1
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(detections)").fetchall()}
        if "ai_class_name" not in cols:
            conn.execute("ALTER TABLE detections ADD COLUMN ai_class_name TEXT")
        cur = conn.execute(
            """
            UPDATE detections
            SET ai_class_name = class_name
            WHERE ai_class_name IS NULL OR ai_class_name = ''
            """
        )
        conn.commit()
        print(f"backfill ai_class_name: {cur.rowcount} rows updated")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
