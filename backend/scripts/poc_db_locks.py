#!/usr/bin/env python
"""PoC P1-2: Benchmark SQLite concurrent writes with different locking strategies.

Tests:
1. No lock (check_same_thread=False only) — baseline
2. threading.Lock around writes only — recommended
3. Global queue (sync) — NOT recommended for async apps

Usage:
    python backend/scripts/poc_db_locks.py
"""
from __future__ import annotations

import logging
import random
import sqlite3
import threading
import time
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import BASE_DIR

logger = logging.getLogger(__name__)

# --- Configuration ---
NUM_WRITERS = 50  # Concurrent writers
OPS_PER_WRITER = 100  # Operations per writer
DB_PATH = BASE_DIR / "test_poc.db"


def _setup_schema(conn: sqlite3.Connection) -> None:
    """Create test schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS test_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS test_lockouts (
            client_key TEXT PRIMARY KEY,
            fail_count INTEGER NOT NULL DEFAULT 0,
            locked_until REAL NOT NULL DEFAULT 0
        );
    """)


def test_no_lock() -> dict[str, float]:
    """Test concurrent writes WITHOUT lock (baseline).
    
    Risk: Data corruption, lost updates, sqlite3.OperationalError.
    """
    logger.info("=" * 60)
    logger.info("Test 1: NO LOCK (baseline)")
    logger.info("=" * 60)
    
    # Clean up
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    # Setup
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _setup_schema(conn)
    conn.close()
    
    # Test
    errors = []
    start_time = time.time()
    
    def writer(writer_id: int) -> None:
        try:
            local_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            for i in range(OPS_PER_WRITER):
                try:
                    key = f"writer_{writer_id}_key_{i % 10}"  # Key collision
                    value = f"value_{writer_id}_{i}"
                    ts = time.time()
                    local_conn.execute(
                        """INSERT OR REPLACE INTO test_settings (key, value, updated_at)
                           VALUES (?, ?, ?)""",
                        (key, value, ts),
                    )
                    local_conn.commit()
                except sqlite3.OperationalError as exc:
                    errors.append(f"Writer {writer_id}: {exc}")
            local_conn.close()
        except Exception as exc:
            errors.append(f"Writer {writer_id} exception: {exc}")
    
    threads = [threading.Thread(target=writer, args=(wid,)) for wid in range(NUM_WRITERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    elapsed = time.time() - start_time
    total_ops = NUM_WRITERS * OPS_PER_WRITER
    rps = total_ops / elapsed if elapsed > 0 else 0
    
    logger.info(f"Completed {total_ops} operations in {elapsed:.2f}s")
    logger.info(f"Throughput: {rps:.0f} ops/sec")
    logger.info(f"Errors: {len(errors)}")
    if errors:
        logger.info(f"Sample errors: {errors[:3]}")
    
    return {
        "test": "no_lock",
        "elapsed": elapsed,
        "ops": total_ops,
        "rps": rps,
        "errors": len(errors),
    }


def test_write_lock() -> dict[str, float]:
    """Test concurrent writes WITH threading.Lock (recommended).
    
    Only locks writes, reads remain concurrent.
    """
    logger.info("=" * 60)
    logger.info("Test 2: WRITE LOCK (recommended)")
    logger.info("=" * 60)
    
    # Clean up
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    # Setup
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _setup_schema(conn)
    conn.close()
    
    # Lock for writes only
    write_lock = threading.Lock()
    errors = []
    start_time = time.time()
    
    def writer(writer_id: int) -> None:
        try:
            local_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            for i in range(OPS_PER_WRITER):
                try:
                    key = f"writer_{writer_id}_key_{i % 10}"  # Key collision
                    value = f"value_{writer_id}_{i}"
                    ts = time.time()
                    
                    # Acquire lock only for write
                    with write_lock:
                        local_conn.execute(
                            """INSERT OR REPLACE INTO test_settings (key, value, updated_at)
                               VALUES (?, ?, ?)""",
                            (key, value, ts),
                        )
                        local_conn.commit()
                except sqlite3.OperationalError as exc:
                    errors.append(f"Writer {writer_id}: {exc}")
            local_conn.close()
        except Exception as exc:
            errors.append(f"Writer {writer_id} exception: {exc}")
    
    threads = [threading.Thread(target=writer, args=(wid,)) for wid in range(NUM_WRITERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    elapsed = time.time() - start_time
    total_ops = NUM_WRITERS * OPS_PER_WRITER
    rps = total_ops / elapsed if elapsed > 0 else 0
    
    logger.info(f"Completed {total_ops} operations in {elapsed:.2f}s")
    logger.info(f"Throughput: {rps:.0f} ops/sec")
    logger.info(f"Errors: {len(errors)}")
    if errors:
        logger.info(f"Sample errors: {errors[:3]}")
    
    return {
        "test": "write_lock",
        "elapsed": elapsed,
        "ops": total_ops,
        "rps": rps,
        "errors": len(errors),
    }


def test_long_lock_contention() -> dict[str, float]:
    """Test lock contention scenario (slow writes).
    
    Simulates slow database writes to ensure queue doesn't overflow.
    """
    logger.info("=" * 60)
    logger.info("Test 3: LOCK CONTENTION (slow writes)")
    logger.info("=" * 60)
    
    # Clean up
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    # Setup
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _setup_schema(conn)
    conn.close()
    
    write_lock = threading.Lock()
    errors = []
    start_time = time.time()
    
    def slow_writer(writer_id: int) -> None:
        try:
            local_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            for i in range(OPS_PER_WRITER):
                try:
                    key = f"writer_{writer_id}_key_{i % 5}"  # More collisions
                    value = f"value_{writer_id}_{i}"
                    ts = time.time()
                    
                    # Simulate slow write (e.g., large transaction)
                    with write_lock:
                        local_conn.execute(
                            """INSERT OR REPLACE INTO test_settings (key, value, updated_at)
                               VALUES (?, ?, ?)""",
                            (key, value, ts),
                        )
                        local_conn.commit()
                        # Simulate slow disk I/O
                        time.sleep(0.001)  # 1ms delay
                except sqlite3.OperationalError as exc:
                    errors.append(f"Writer {writer_id}: {exc}")
            local_conn.close()
        except Exception as exc:
            errors.append(f"Writer {writer_id} exception: {exc}")
    
    threads = [threading.Thread(target=slow_writer, args=(wid,)) for wid in range(NUM_WRITERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    elapsed = time.time() - start_time
    total_ops = NUM_WRITERS * OPS_PER_WRITER
    rps = total_ops / elapsed if elapsed > 0 else 0
    
    logger.info(f"Completed {total_ops} operations in {elapsed:.2f}s")
    logger.info(f"Throughput: {rps:.0f} ops/sec")
    logger.info(f"Errors: {len(errors)}")
    if errors:
        logger.info(f"Sample errors: {errors[:3]}")
    
    return {
        "test": "lock_contention",
        "elapsed": elapsed,
        "ops": total_ops,
        "rps": rps,
        "errors": len(errors),
    }


def main() -> None:
    """Run all PoC tests."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    logger.info("PoC P1-2: SQLite Locking Strategies Benchmark")
    logger.info(f"Configuration: {NUM_WRITERS} writers, {OPS_PER_WRITER} ops each")
    logger.info(f"Database: {DB_PATH}")
    logger.info("")
    
    results = []
    
    # Test 1: No lock
    results.append(test_no_lock())
    logger.info("")
    
    # Clean up between tests
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    # Test 2: Write lock
    results.append(test_write_lock())
    logger.info("")
    
    # Clean up between tests
    if DB_PATH.exists():
        DB_PATH.unlink()
    
    # Test 3: Lock contention
    results.append(test_long_lock_contention())
    
    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"{'Test':<25} {'RPS':<12} {'Errors':<10} {'Time (s)':<12}")
    logger.info("-" * 60)
    for r in results:
        logger.info(
            f"{r['test']:<25} {r['rps']:<12.0f} {r['errors']:<10} {r['elapsed']:<12.2f}"
        )
    
    logger.info("")
    logger.info("RECOMMENDATION:")
    logger.info("- No lock: Fast but risky (data corruption)")
    logger.info("- Write lock: Safe, good performance, RECOMMENDED")
    logger.info("- Lock contention: Shows lock bottleneck under slow writes")
    logger.info("")
    logger.info("Use threading.Lock() ONLY for writes (INSERT/UPDATE/DELETE).")
    logger.info("READS (SELECT) can run concurrently in WAL mode without lock.")
    
    # Clean up test database
    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info(f"Cleaned up test database: {DB_PATH}")


if __name__ == "__main__":
    main()
