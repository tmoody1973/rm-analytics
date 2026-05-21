"""
Smoke test for the Phase 6 loader foundation.

Proves the whole chain works end-to-end against the REAL Neon database using a
50-row slice of the Q1 hourly export:
  read xlsx -> _common helpers -> load_q1_hourly.load() -> bulk_upsert -> Neon.

Leaves wms.fact_hourly_listening EMPTY afterward so the real backfill starts clean.

Run:  python tests/test_smoke_q1.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "loaders"))

import load_q1_hourly  # noqa: E402
from _common import get_db_connection  # noqa: E402

SRC = os.path.join(ROOT, "exports", "Q1_hourly_2024-01-01_2026-05-16.xlsx")
TABLE = "wms.fact_hourly_listening"
N = 50


def _count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
        return cur.fetchone()[0]


def run() -> None:
    # 1. Read 50 rows of the real export.
    df = pd.read_excel(SRC, nrows=N)
    assert len(df) == N, f"expected {N} source rows, got {len(df)}"

    # 2. Write them to a throwaway xlsx the loader can open.
    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    df.to_excel(tmp_path, index=False)

    try:
        conn = get_db_connection()
        try:
            # Precondition: table must be empty so COUNT == upserted is meaningful.
            before = _count(conn)
            assert before == 0, (
                f"{TABLE} is not empty before the smoke test ({before} rows); "
                "aborting so we don't mix test rows with existing data"
            )
        finally:
            conn.close()

        # 3. Run the loader under test.
        stats = load_q1_hourly.load(tmp_path)

        # 4. It reports 50 rows upserted.
        assert stats["rows_upserted"] == N, (
            f"expected rows_upserted == {N}, got {stats['rows_upserted']}"
        )

        # 5/6. The database actually holds that many rows.
        conn = get_db_connection()
        try:
            after = _count(conn)
            assert after == stats["rows_upserted"], (
                f"DB count {after} != rows_upserted {stats['rows_upserted']}"
            )

            # 7. Clean up so the real backfill starts from an empty table.
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM {TABLE}")
            conn.commit()
            final = _count(conn)
            assert final == 0, f"cleanup failed, {TABLE} still has {final} rows"
        finally:
            conn.close()
    finally:
        os.unlink(tmp_path)

    print(
        f"   read={stats['rows_read']} upserted={stats['rows_upserted']} "
        f"db_count={after} after_cleanup={final} elapsed={stats['elapsed_sec']}s"
    )
    print("✅ smoke test passed")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        print("❌ smoke test FAILED")
        traceback.print_exc()
        sys.exit(1)
