# Manually pulling a month of streaming from Triton

> ## ⏰ TODO — first week of October 2026
> Pull **August _and_ September** monthly (Cume, Geography, Device) from Triton.
> - **August** also arrives on its own ~Oct 1 (scheduled).
> - **September** will NOT arrive until Nov 1 unless pulled manually — so grab both in one sitting.
> - Only works once the month has **closed** (after Sept 30) — a monthly CUME needs the full month.
> - Export from Triton → drop the XLSX files in `exports/` → tell Claude *"load the Aug + Sept exports."*
> - Delete this box once both months are loaded and verified.

**Use this when** the monthly streaming rollups are behind and you need a month
*now* instead of waiting for the scheduled email.

**Why you'd need it:** the three *monthly* Triton reports arrive on a ~2-month
lag — the export sent on the 1st carries the month that ended ~5 weeks earlier
(June landed Aug 1, July landed Sept 1, **August lands Oct 1**). The *daily*,
*hourly*, and *weekly* feeds are same-week, so this guide is only for the
**monthly** tables (and for backfilling any daily days that got skipped).

Everything here is **idempotent** — re-running a load just refreshes those rows,
never duplicates. Safe to repeat.

---

## What you're pulling

| Triton report | Loads into | Loader | Subject tag |
|---|---|---|---|
| Monthly **Cume** | `wms.fact_monthly_cume` | `load_q2c_monthly_cume.py` | `[WMS-Q2C-CUME-MONTHLY]` |
| Monthly **Geography** | `wms.fact_monthly_geo` | `load_q3_monthly_geo.py` | `[WMS-Q3-GEO]` |
| Monthly **Device** | `wms.fact_monthly_device` | `load_q4_monthly_device.py` | `[WMS-Q4-DEVICE]` |
| *(gap-fill)* Daily **Cume** | `wms.fact_daily_cume` | `load_q2a_daily_cume.py` | `[WMS-Q2A-CUME-DAILY]` |
| *(gap-fill)* **Hourly** | `wms.fact_hourly_listening` | `load_q1_hourly.py` | `[WMS-Q1-HOURLY]` |

---

## Step 1 — Export from Triton (the part only you can do)

In the Triton portal (Webcast Metrics). Detailed UI navigation + screenshots
live in **`docs/triton-scheduled-queries-setup.md`** — this is the short version.

For **each** of the three monthly reports (Cume, Geography, Device):

1. Open the saved report.
2. Set the date range / **Month** dimension to the target month — e.g. **Aug 1 – Aug 31, 2026**.
3. Run it, then **Export → XLSX** (same spreadsheet format the scheduled emails send).
4. Save the file with a clear name, e.g. `Q2c_monthly_cume_2026-08.xlsx`.

**Gap-fill (optional):** if specific *daily* days are missing (we saw Aug 12, 13,
22 skipped), open **Daily Cume**, set the range to the whole month (Aug 1–31 —
idempotent, so re-loading present days is harmless), and export XLSX too.

**The one catch:** this only works if Triton has that month *finalized* on its
side. You'll know the moment you set the date range — if August rows come out,
you're good. If the export is empty for August, Triton hasn't closed it yet and
the Oct-1 scheduled email is the only path. (Daily/weekly are unaffected — those
are always current.)

---

## Step 2 — Get the files into the warehouse

**Recommended — hand them to Claude:** drop the `.xlsx` files in
`~/code/rm-analytics/exports/` (gitignored) and say "load the August exports."
Claude runs the loaders and verifies the rows landed. This is the path with a
confirmation at the end.

Run manually if you prefer:
```bash
cd ~/code/rm-analytics
source .venv/bin/activate
python loaders/load_q2c_monthly_cume.py  exports/Q2c_monthly_cume_2026-08.xlsx
python loaders/load_q3_monthly_geo.py    exports/Q3_monthly_geo_2026-08.xlsx
python loaders/load_q4_monthly_device.py exports/Q4_monthly_device_2026-08.xlsx
# gap-fill, if you pulled daily:
python loaders/load_q2a_daily_cume.py    exports/Q2a_daily_cume_2026-08.xlsx
```
Each prints how many rows it upserted.

**Alternative — email path:** the scheduled pipeline ingests by emailing the XLSX
to the AgentMail inbox with the **subject starting with the tag** (e.g.
`[WMS-Q2C-CUME-MONTHLY] Aug manual`). Only works if your sending address is on the
AgentMail `ALLOWED_INBOX` allowlist — otherwise it's silently rejected, so the
loader path above is the safe bet for a one-off.

---

## Step 3 — Verify

Quick check that August landed (Claude does this automatically after loading):
```bash
python - <<'PY'
import os, psycopg
from pathlib import Path
os.environ["DATABASE_URL"]=next(l.split("=",1)[1].strip().strip('"')
  for l in Path.home().joinpath(".radio-milwaukee/.env").read_text().splitlines()
  if l.startswith("DATABASE_URL="))
c=psycopg.connect(os.environ["DATABASE_URL"]); cur=c.cursor()
for t in ("fact_monthly_cume","fact_monthly_geo","fact_monthly_device"):
    cur.execute(f"select count(*) from wms.{t} where month_start='2026-08-01'")
    print(f"  wms.{t}: {cur.fetchone()[0]} August rows")
PY
```
Then reload the dashboard — the monthly streaming cards and the chat's streaming
metrics (both read `wms.fact_monthly_cume`) will show August.

---

## Preventing the surprise

The daily "a feed went stale" alert (`jobs/check_freshness.py`, Fly machine
`freshness-check-daily`) watches streaming freshness and Slacks you if a feed
stops — so a missed month or skipped daily day pings you within a day instead of
being noticed weeks later.
