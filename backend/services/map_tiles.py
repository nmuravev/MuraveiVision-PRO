"""Offline map tiles: folder XYZ and MBTiles (TMS), stdlib only."""
from __future__ import annotations

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
TILES_DIR = BASE_DIR / "assets" / "map_tiles"
MBTILES_PATH = BASE_DIR / "assets" / "map_tiles.mbtiles"


def tiles_available() -> bool:
    if TILES_DIR.is_dir() and any(TILES_DIR.rglob("*.png")):
        return True
    if MBTILES_PATH.is_file() and MBTILES_PATH.stat().st_size > 0:
        return True
    return False


def get_tile_bytes(z: int, x: int, y: int) -> bytes | None:
    """Return PNG bytes for XYZ tile, or None if missing.

    MBTiles store TMS row: y_tms = (2**z - 1) - y.
    """
    if z < 0 or z > 22 or x < 0 or y < 0:
        return None

    folder_tile = TILES_DIR / str(z) / str(x) / f"{y}.png"
    if folder_tile.is_file():
        try:
            return folder_tile.read_bytes()
        except OSError:
            return None

    if not MBTILES_PATH.is_file():
        return None

    y_tms = (2**z - 1) - y
    try:
        conn = sqlite3.connect(f"file:{MBTILES_PATH.as_posix()}?mode=ro", uri=True)
        try:
            cur = conn.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, y_tms),
            )
            row = cur.fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None

    if not row or not row[0]:
        return None
    data = row[0]
    return bytes(data) if not isinstance(data, bytes) else data
