# Triton Backfill — Closing the Gap (May 18 → June 4)

> **What this is:** A step-by-step guide to fill in the missing streaming data
> between when the first backfill ended and when the daily pipeline took over.
> **Who it's for:** You, doing this by hand once. No coding knowledge needed —
> you do the Triton clicking, then copy-paste 3 commands.
> **Time:** ~20 minutes.

---

## Why we need this

The original backfill loaded everything **up to 2026-05-17**. The automated
daily pipeline only started landing data around **2026-06-05**. That leaves a
hole in the middle:

```
2024-01-01 ──────── 2026-05-17   [GAP]   2026-06-05 ──── today
   ✅ backfilled ✅            ❌ missing        ✅ daily pipeline ✅
```

**The missing window is May 18 through June 4, 2026** (18 days) for the daily
and hourly numbers, plus 4 missing weeks for the weekly cume.

The daily pipeline will **never** fill this on its own — it only ever grabs
"yesterday" or "last week," so the past stays missing unless we go get it
manually. That's what this guide does.

**Good news:** the loaders are safe to re-run. If a date you export already
exists in the database, it just gets harmlessly overwritten with the same
values. So you don't have to be surgical about exact date boundaries — a
little overlap is fine.

---

## What you'll do (the big picture)

For each of **3 queries** (Q1, Q2a, Q2b), you'll:

1. Open the query in Triton
2. Change its date range to the gap window
3. Export the file (CSV or XLSX — both work)
4. Save it to the `exports/` folder on your laptop
5. Run one command to load it into Neon

Then one final command to confirm the gap is closed.

---

## Before you start

Open Terminal and run these two lines once. Leave the window open — you'll
paste the load commands into it later.

```bash
cd ~/code/rm-analytics
source .venv/bin/activate
```

If your prompt now starts with `(.venv)`, you're ready.

---

## ⚠️ One important note about which query to use

You have **two versions** of each query in Triton:

| Version | Has a `[WMS-…]` tag in the name? | Use it for… |
|---|---|---|
| **Bulk** (historical) | No tag | **← USE THIS ONE for backfill** |
| **Scheduled** (daily) | Yes, starts with `[WMS-…]` | Leave alone — it runs automatically |

For this backfill, use the **Bulk** versions — the ones you used for the
original 2024→2026 load. They have flexible date ranges. **Do not change the
Scheduled queries' dates** or you'll break tomorrow's automatic run.

> If you can't find a separate Bulk query, you can use the Scheduled one — but
> after exporting, you **must** set its date range back to the rolling preset
> (`Last day` / `Last week`) before you leave, or the next morning's automatic
> run will pull the wrong dates.

---

## Query 1 of 3 — Q1 Hourly Listening

**In Triton:**

1. Open **Saved Queries** and click your **Bulk Q1 Hourly** query
2. Click the date-range filter (the middle button that shows the current dates)
3. In the **Date Range** panel, choose **Custom Range**
4. Set the two date boxes to:
   - From: **2026-05-18**
   - To: **2026-06-07**
5. Click **Apply and Run**
6. Confirm the report below shows rows with dates in that window, all 4 stations
7. Click **Export** → choose **CSV** (or XLSX — either is fine)
8. Save the downloaded file into this exact folder, with this exact name:

   ```
   ~/code/rm-analytics/exports/Q1_hourly_gap.csv
   ```

   (If you exported XLSX instead, name it `Q1_hourly_gap.xlsx`.)

**In Terminal**, paste:

```bash
python loaders/load_q1_hourly.py exports/Q1_hourly_gap.csv
```

(Use `.xlsx` at the end instead if that's what you saved.)

✅ **Expected result:** something like
`[Q1 Hourly] upserted ~1800 rows into wms.fact_hourly_listening`.
The exact number will vary, but it should be in the high hundreds to a couple
thousand.

---

## Query 2 of 3 — Q2a Daily Cume

**In Triton:**

1. Open your **Bulk Q2a Daily Cume** query
2. Date range → **Custom Range**:
   - From: **2026-05-18**
   - To: **2026-06-07**
3. **Apply and Run**, confirm the preview
4. **Export** → CSV or XLSX
5. Save as:

   ```
   ~/code/rm-analytics/exports/Q2a_daily_gap.csv
   ```

**In Terminal:**

```bash
python loaders/load_q2a_daily_cume.py exports/Q2a_daily_gap.csv
```

✅ **Expected result:**
`[Q2a Daily cume] upserted ~80 rows into wms.fact_daily_cume`
(roughly 4 stations × ~20 days).

---

## Query 3 of 3 — Q2b Weekly Cume

This one needs a **wider** date range to catch all the missing weeks.

**In Triton:**

1. Open your **Bulk Q2b Weekly Cume** query
2. Date range → **Custom Range**:
   - From: **2026-05-12**
   - To: **2026-06-08**
3. **Apply and Run**, confirm the preview
4. **Export** → CSV or XLSX
5. Save as:

   ```
   ~/code/rm-analytics/exports/Q2b_weekly_gap.csv
   ```

**In Terminal:**

```bash
python loaders/load_q2b_weekly_cume.py exports/Q2b_weekly_gap.csv
```

✅ **Expected result:**
`[Q2b Weekly cume] upserted ~16 rows into wms.fact_weekly_cume`
(roughly 4 stations × 4 weeks).

---

## Final step — confirm the gap is closed

Paste this whole block into Terminal:

```bash
python - <<'PY'
import sys; sys.path.insert(0, "loaders")
from _common import get_db_connection
from datetime import date, timedelta

conn = get_db_connection()
with conn.cursor() as cur:
    cur.execute("""
        SELECT date FROM wms.fact_hourly_listening
        WHERE date BETWEEN DATE '2026-05-18' AND DATE '2026-06-07'
        GROUP BY date
    """)
    present = {str(r[0]) for r in cur.fetchall()}

d, end, missing = date(2026,5,18), date(2026,6,7), []
while d <= end:
    if str(d) not in present:
        missing.append(str(d))
    d += timedelta(days=1)

if missing:
    print("STILL MISSING these days:", missing)
else:
    print("✅ No gaps — every day from 2026-05-18 to 2026-06-07 is present.")
conn.close()
PY
```

- If it prints **✅ No gaps** — you're done. The streaming data is complete.
- If it lists **STILL MISSING** days — those days may genuinely have no data
  in Triton, OR the export didn't cover them. Re-check the date range on that
  query and re-export. If a day is missing in Triton itself, that's expected
  (e.g. a station outage) — send me the list and I'll confirm.

---

## If something goes wrong

| Symptom | What it means | Fix |
|---|---|---|
| `FileNotFoundError` when running a load command | The file name/location doesn't match | Check the file is in `~/code/rm-analytics/exports/` and the name matches the command exactly |
| `export is missing expected columns` | Triton's column headers changed, or you exported the wrong query | Re-export; make sure you ran the right Q-number query |
| Export downloads but is empty / header only | That date range has no data in Triton | Double-check the dates; some ranges genuinely have gaps |
| `upserted 0 rows` | The file had no data rows | Re-open it — likely an empty export |
| Triton won't let you pick a recent date | Triton's data isn't finalized yet (it lags ~4 days) | Use an end date no later than ~5 days ago; the daily pipeline covers the rest |

When in doubt, paste the Terminal output to me and I'll tell you exactly what
happened.

---

## What you do NOT need to backfill

- **Q2c Monthly Cume, Q3 Geography, Q4 Device** — these are already current
  through May 2026, and the next monthly scheduled run (July 1) fills June
  automatically. Skip them.
- **The most recent 3–4 days** (June 8 onward) — Triton hasn't finalized them
  yet. The daily pipeline will pick them up on its own as they become
  available. Don't chase them.
