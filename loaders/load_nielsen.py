"""
Nielsen PPM "Vital Signs Trend" loader (manual, ~monthly, per station/demo/daypart).

The export is a pivoted wide grid: metrics down the rows, ~14 survey periods across
the columns, grouped into sections (Estimates, P1 Information, In-Tab, Detailed
Daypart Trend, Age/Gender/Ethnic Composition). This loader UNPIVOTS it into
nielsen.fact_vital_signs — one row per (station, demo, daypart, period, section,
metric). Idempotent upsert, so re-uploading overlapping trend reports (each carries
the last ~14 months) just refreshes values (Nielsen occasionally revises).

Each report self-describes: station from the title line, demo + daypart + market
from the preamble. So HYFIN vs Radio Milwaukee and different dayparts/demos all
coexist with no collision. Unknown station names fail loudly.

Licensed/confidential Nielsen data — keep internal.

CLI:  python loaders/load_nielsen.py "exports/.../PDAWeb_VitalSignsTrend_*.csv"
"""
from __future__ import annotations

import csv
import re
import sys
import time
from datetime import date

from _common import bulk_upsert, get_db_connection

# Report title display-name -> internal station_code. Fails loudly if unmatched.
STATION_MAP = {
    "radio milwaukee": "RM88",
    "88nine": "RM88",
    "hyfin": "HYFIN",
    "414 music": "RM414",
    "rhythm lab radio": "RLR",
}

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}

TABLE = "nielsen.fact_vital_signs"
COLUMNS = ["station_code", "market", "demo", "daypart", "period_label", "period_date",
           "section", "metric", "value_numeric", "value_raw", "rank", "unit"]
CONFLICT = ["station_code", "demo", "daypart", "period_label", "section", "metric"]
UPDATE = [c for c in COLUMNS if c not in CONFLICT]

_PERIOD_RE = re.compile(r"^[A-Z]{3}\d{2}$")          # MAY25, HOL25, JAN26
_RANK_RE = re.compile(r"^([\d.]+)\s*\((\d+)t?\)$")   # "2.2 (18)" / "2.3 (17t)"
_TIME_RE = re.compile(r"^\d+:\d{2}$")                 # "1:15"
_DAYPART_RE = re.compile(r"\d{1,2}[apm]")             # time token inside a daypart string


def _period_date(label: str):
    """Map a Nielsen survey label to a sortable date. Regular months -> 1st of month.
    HOL (the Holiday book — a distinct survey between the Dec and Jan books) -> Dec 15
    of its year, so it charts chronologically between DEC and JAN. The period_label
    ('HOL25') still distinguishes it from the regular December book."""
    try:
        yy = int(label[3:5])
    except ValueError:
        return None
    if label[:3] == "HOL":
        return date(2000 + yy, 12, 15)
    mon = MONTHS.get(label[:3])
    return date(2000 + yy, mon, 1) if mon else None


def _station_code(rows: list[list[str]], override: str | None) -> str:
    if override:
        return override
    blob = " ".join(c for r in rows[:5] for c in r)
    m = re.search(r"How Are \*?(.+?)'s Vital Signs", blob)
    name = (m.group(1) if m else blob).lower()
    for key, code in STATION_MAP.items():
        if key in name:
            return code
    raise ValueError(f"Could not map a station from report title {name!r}; "
                     f"known: {sorted(STATION_MAP)}")


def _preamble(rows: list[list[str]]) -> tuple[str | None, str | None, str | None]:
    """Return (market, demo, daypart) parsed from the ';'-delimited preamble rows."""
    market = demo = daypart = None
    for r in rows[:6]:
        text = ",".join(r)
        if ";" not in text:
            continue
        parts = [p.strip().strip('"') for p in text.split(";")]
        if any("Metro" in p or "DMA" in p for p in parts) and market is None:
            market = parts[0]
        if any(re.search(r"Persons|Adults|Women|Men", p) for p in parts):
            for p in parts:
                if re.search(r"Persons|Adults|Women|Men", p) and "Threshold" not in p:
                    demo = demo or p
                elif _DAYPART_RE.search(p) and "Threshold" not in p and "-" in p:
                    daypart = daypart or p
    return market, demo, daypart


def _parse_value(raw: str, label: str, section: str):
    """Return (value_numeric, rank, unit) for a cell; None if blank/unparseable.
    Unit is inferred from BOTH the row label and the section header (e.g. the
    'Detailed Daypart Trend (AQH Share)' rows are shares even though the row label
    is just a daypart like 'M-F 6a-10a')."""
    raw = raw.strip()
    if not raw:
        return None
    m = _RANK_RE.match(raw)
    if m:
        return float(m.group(1)), int(m.group(2)), "share"
    if raw.endswith("%"):
        try:
            return float(raw[:-1].replace(",", "")), None, "percent"
        except ValueError:
            return None
    if _TIME_RE.match(raw):
        h, mn = raw.split(":")
        return float(int(h) * 60 + int(mn)), None, "minutes"
    try:
        num = float(raw.replace(",", ""))
    except ValueError:
        return None
    ctx = f"{label} {section}".lower()
    if "share" in ctx:
        unit = "share"
    elif "rating" in ctx:
        unit = "rating"
    elif "occasion" in ctx:
        unit = "occasions"
    elif "panelist" in ctx or "in-tab" in ctx:
        unit = "panelists"
    else:
        unit = "persons"
    return num, None, unit


def load(file_path: str, station_override: str | None = None) -> dict:
    start = time.time()
    with open(file_path, encoding="utf-8-sig", errors="replace") as fh:
        rows = list(csv.reader(fh))

    station = _station_code(rows, station_override)
    market, demo, daypart = _preamble(rows)
    demo = demo or "Unknown"
    daypart = daypart or "Unknown"

    # Locate the period header row (>=3 cells matching the period pattern).
    header_idx = next((i for i, r in enumerate(rows)
                       if sum(bool(_PERIOD_RE.match(c.strip())) for c in r) >= 3), None)
    if header_idx is None:
        raise ValueError("not a Vital Signs export: no period header row "
                         "(e.g. MAY25, JUN25, ...) found")
    periods = [(j, c.strip()) for j, c in enumerate(rows[header_idx])
               if _PERIOD_RE.match(c.strip())]   # excludes "14-Month Average" + blanks

    out_rows: list[tuple] = []
    section = None
    for r in rows[header_idx + 1:]:
        label = (r[0].strip() if r else "")
        if not label or label.startswith("Copyright"):
            continue
        cells = {j: r[j].strip() for j, _ in periods if j < len(r)}
        if not any(cells.values()):       # no period values => section header
            section = label
            continue
        if section is None:
            continue
        for j, plabel in periods:
            parsed = _parse_value(cells.get(j, ""), label, section)
            if parsed is None:
                continue
            val, rank, unit = parsed
            out_rows.append((station, market, demo, daypart, plabel, _period_date(plabel),
                             section, label, val, r[j].strip(), rank, unit))

    conn = get_db_connection()
    try:
        n = bulk_upsert(conn, TABLE, COLUMNS, out_rows, CONFLICT, UPDATE)
    finally:
        conn.close()

    return {
        "file": file_path.split("/")[-1],
        "table": TABLE,
        "station": station, "demo": demo, "daypart": daypart, "market": market,
        "periods": len(periods), "rows_upserted": n,
        "elapsed_sec": round(time.time() - start, 1),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: python loaders/load_nielsen.py FILE [FILE ...]")
    for path in sys.argv[1:]:
        print(load(path))
