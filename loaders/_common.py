"""
Shared helpers for the WMS (Triton) backfill loaders.

Every per-query loader imports from here so the station mapping, TSL parsing,
DB connection, and bulk upsert logic live in exactly one place.

psycopg3 (the `psycopg` package). Import is `import psycopg`, NOT psycopg2.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Station mapping — raw Triton "Station" string -> internal station_code.
# Source of truth: CLAUDE.md "Station code mapping".
# ---------------------------------------------------------------------------
STATION_MAP: dict[str, str] = {
    "WYMSFM": "RM88",
    "WYMSHD2": "HYFIN",
    "414 Music": "RM414",
    "Rhythm Lab Radio 24/7": "RLR",
}


def resolve_station(triton_station: object) -> str:
    """Map a raw Triton station string to its internal station_code.

    Raises ValueError on an unknown station so a bad export fails loudly
    rather than silently loading rows under a wrong/empty code.
    """
    key = str(triton_station).strip()
    code = STATION_MAP.get(key)
    if code is None:
        raise ValueError(
            f"Unknown Triton station {key!r}; expected one of {sorted(STATION_MAP)}"
        )
    return code


# ---------------------------------------------------------------------------
# Numeric / text coercion. Triton leaves empties as "" and pandas turns missing
# cells into float NaN — both must become a clean 0 / 0.0 / "" before insert.
# ---------------------------------------------------------------------------
def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == "" or str(value).strip().lower() == "nan"


def coerce_int(value: object) -> int:
    """Empty / NaN / None -> 0; otherwise int (via float to tolerate '12.0')."""
    if _is_blank(value):
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def coerce_float(value: object) -> float:
    """Empty / NaN / None -> 0.0; otherwise float."""
    if _is_blank(value):
        return 0.0
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return 0.0


def coerce_str(value: object) -> str:
    """NaN / None -> '' ; otherwise stripped string (for text PK components)."""
    if _is_blank(value):
        return ""
    return str(value).strip()


def read_export(file_path: str) -> "pd.DataFrame":
    """Read a Triton export, auto-detecting CSV vs XLSX by extension.

    Triton's scheduled queries default to CSV (wrapped in a ZIP when forwarded
    through Gmail), while bulk/historical exports come down as XLSX. Both share
    the same column headers, so the only thing that changes is the reader.
    """
    p = str(file_path).lower()
    if p.endswith(".csv"):
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)


def parse_tsl(s: object) -> float:
    """Convert Triton TSL "HH:MM" to total minutes. "00:46" -> 46.0.

    Empty / NaN -> 0.0. Falls back to a plain numeric string if there is no ':'.
    """
    if _is_blank(s):
        return 0.0
    text = str(s).strip()
    if ":" in text:
        parts = text.split(":")
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            return float(hours * 60 + minutes)
        except (ValueError, IndexError):
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Column inspection — each loader calls this before parsing so a renamed Triton
# column is caught immediately with a clear message, not as a KeyError mid-loop.
# ---------------------------------------------------------------------------
def assert_columns(df, expected: list[str], query_name: str) -> None:
    found = list(df.columns)
    print(f"[{query_name}] export columns: {found}")
    missing = [c for c in expected if c not in found]
    if missing:
        raise ValueError(
            f"[{query_name}] export is missing expected columns {missing}; "
            f"got {found}"
        )


# ---------------------------------------------------------------------------
# Database. DATABASE_URL lives in ~/.radio-milwaukee/.env (chmod 600, gitignored).
# ---------------------------------------------------------------------------
ENV_PATH = Path.home() / ".radio-milwaukee" / ".env"


def get_db_connection() -> psycopg.Connection:
    """Open a psycopg3 connection using DATABASE_URL from the environment.

    Loads ~/.radio-milwaukee/.env if the var is not already set.
    """
    if not os.environ.get("DATABASE_URL") and ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(f"DATABASE_URL not set (expected in env or {ENV_PATH})")
    return psycopg.connect(dsn)


def bulk_upsert(
    conn: psycopg.Connection,
    table: str,
    columns: list[str],
    rows: list[tuple],
    conflict_columns: list[str],
    update_columns: list[str],
    batch_size: int = 5000,
) -> int:
    """INSERT ... ON CONFLICT DO UPDATE in batches via psycopg3 executemany.

    `table`, `columns`, `conflict_columns`, `update_columns` are trusted internal
    identifiers defined by the loaders (never external input), so they are safe to
    interpolate. Row VALUES are always passed as parameters. Commits once at the end.
    Returns the number of rows sent.
    """
    if not rows:
        return 0

    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    conflict_list = ", ".join(conflict_columns)
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
    sql = (
        f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_list}) DO UPDATE SET {set_clause}"
    )

    total = 0
    with conn.cursor() as cur:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            cur.executemany(sql, batch)
            total += len(batch)
    conn.commit()
    return total
