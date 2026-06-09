# Triton WMS — Scheduled Queries Setup Guide

> **Audience:** Anyone who has not used Triton's "Save & Schedule" feature before.
> **Time to complete:** about 45 minutes, once.
> **Last updated:** 2026-06-09 (Phase 8 of the Radio Milwaukee analytics build).

This guide walks you through setting up **6 recurring queries** in
Triton Webcast Metrics (WMS) so they automatically email XLSX exports to our
`triton-ingest@agentmail.to` inbox. From there, our Fly.io webhook
(`rm-data-loader`) parses each export and writes the rows into Neon
Postgres — without anyone touching anything.

You only have to do this once. After it's set up, the pipeline runs on its
own every day, every Monday, and every 1st of the month.

---

## What you'll have when you're done

A pipeline that runs itself:

```
Triton scheduled query
     │  (daily / weekly / monthly)
     ▼
Email with XLSX attachment
     │  to:      triton-ingest@agentmail.to
     │  subject: contains "[WMS-Q1-HOURLY]" (or similar tag)
     ▼
AgentMail inbox
     │  webhook → POST /webhook/wms
     ▼
rm-data-loader on Fly.io
     │  verifies signature, parses XLSX
     ▼
Neon Postgres — wms.fact_* tables
```

If anything in that chain breaks, you'll see it in **Slack** (a ❌) or in
**Fly.io logs** (`flyctl logs --app rm-data-loader`).

---

## The single most important concept (read this twice)

**Triton's schedule feature does NOT let you customize the email subject line.
The email subject is exactly the name you give the saved query.**

That matters because our webhook router decides which loader to run by
looking for a "tag" in the subject line — strings like `[WMS-Q1-HOURLY]`
or `[WMS-Q3-GEO]`. Without the right tag, the email arrives but nothing
happens to it.

**So the tag MUST be part of the saved-query NAME.** Every query name in
this guide starts with its tag, in square brackets, exactly as written. Do
not change them, do not drop the brackets, do not change the capitalization.

Good name: `[WMS-Q1-HOURLY] Hourly Listening (all 4 stations)`
Bad name:  `WMS Q1 Hourly` ← no brackets, won't route
Bad name:  `[wms-q1-hourly] Hourly` ← lowercase tag, won't route

---

## Before you start — prerequisites

You need ALL of these to be true. If any one is false, fix it before going
further.

1. **You can log into Triton Webcast Metrics.**
   You see the Query Builder ("Explore") and can run a one-off query.

2. **Our AgentMail inbox is live.**
   `triton-ingest@agentmail.to` exists and can receive mail. Verify by
   sending it a quick test email from any account.

3. **The Fly.io webhook is deployed.**
   ```bash
   curl https://rm-data-loader.fly.dev/health
   ```
   should return `{"ok":true,"routes":["[WMS-Q1-HOURLY]", ...]}` with
   HTTP 200. If you get anything else, fix the deploy first.

4. **The AgentMail webhook is registered.**
   `flyctl secrets list --app rm-data-loader` should show
   `AGENTMAIL_WEBHOOK_SECRET` as `Deployed`. (If not, run
   `python jobs/register_agentmail_webhook.py` and follow its output.)

5. **(Optional but recommended) Whitelist Triton's sender.**
   Triton's scheduled emails come from `noreply@tritondigital.com`. If
   AgentMail has any spam filter, allow that address.

---

## The general pattern — what every scheduled query looks like

Each of the 6 queries is set up the same way. Once you've done Q1, the
other five are just "the same, but with different columns and a different
cadence."

The pattern is:

1. **Build the query** in Query Builder ("Explore"). Pick the right
   dimensions, metrics, stations, and date range.
2. **Save it** with the exact name from this doc (tag in brackets, then a
   human label).
3. **Schedule it** — set recipient, format, frequency, time.
4. **Verify** — wait for the next scheduled run, then check Neon.

You'll repeat this 6 times. There's a checklist at the end of the doc.

---

## How to save and schedule any query (the mechanics)

The buttons and labels below are from Triton's official
"Saving & Scheduling Queries" docs.

### Save the query

1. After building your query and confirming the preview looks right, click
   **Save** at the bottom right of the query builder.
2. In the dialog, enter the **query name** (this is the part that ends up
   as the email subject). Keep it under 255 characters.
3. Click **Save New Query**.

If you ever need to edit a saved query, the button at the bottom changes
to **Update Query** (with an option to save as a new query under a
different name).

### Open your saved query later

Saved queries live in the **Saved Queries** list — there's a dedicated
button in the Triton UI to open it.

### Add a schedule

There are two ways to start scheduling:

- From inside the Query Builder: click **Schedule** at the bottom.
- From the **Saved Queries** list: open the query's options menu and pick
  **Add Schedule**.

A schedule form will open. Fill it in:

| Field | What to set | Notes |
|---|---|---|
| **Email** | `triton-ingest@agentmail.to` | Type the address, click **Add**. |
| **Email (extras, optional)** | `tarik@radiomilwaukee.org` | Optional — gives you a copy for sanity checks. Leave off if you don't want noise in your inbox. |
| **Interval** | Daily / Weekly / Monthly | Use exactly what each query section below says. |
| **Day** (Weekly only) | Monday | For Q2b only. |
| **Day** (Monthly only) | **1** | For Q2c, Q3, Q4. Triton's own docs say day "1" is the safest because days 29–31 may skip months. |
| **Time** | See per-query times below | All times are Central Time. |
| **Timezone** | Central Time (US) | Same for all 6. |

Click **Save** / **Add Schedule** to confirm.

### Edit or delete a schedule

- **Edit:** in the Saved Queries list, click the small schedule icon next
  to the query, or use the options menu → **Edit Schedule**.
- **Delete:** from the same options menu.

### Limits Triton enforces (don't trip these)

- **Maximum 30 scheduled queries per account.** We use 6 — plenty of room.
- **You cannot schedule a query with a fixed date range.** It must use a
  **rolling** preset. Triton's Date Range dialog offers these presets:
  `Last day`, `Last full day`, `Last 7 days`, `Last week`, `Last 30 days`,
  `Last month`, `Last 90 days`. Each section below tells you which preset
  to use.
- **Schedule time must be after 11:00 UTC.** This is Triton's rule to make
  sure the previous period's data is fully aggregated before they send.
  All of our times (the earliest is 6:30 a.m. CT = 11:30 UTC in summer)
  are safely past it.

---

## Per-query setup

For each of the 6 queries, the recipient is always the same
(`triton-ingest@agentmail.to`), the format is always **XLSX**, and the
timezone is always **Central Time (US)**. Below I only list the
per-query differences.

### Q1 — Hourly Listening

> The most active table. ~96 rows per day (4 stations × 24 hours).
> Powers the Program Director hourly tune-out chart.

| Item | Value |
|---|---|
| **Saved query name** | `[WMS-Q1-HOURLY] Hourly Listening (all 4 stations)` |
| **Stations** | WYMSFM, WYMSHD2, 414 Music, Rhythm Lab Radio 24/7 |
| **Dimensions** | Station, Date Hour |
| **Metrics** | AAS, TLH, CUME, SS, TSL |
| **Date range** | `Last day` (the highlighted default preset) |
| **Schedule interval** | Daily |
| **Schedule time** | 06:30 Central Time |
| **Target table in Neon** | `wms.fact_hourly_listening` |

**Why this time:** 06:30 CT = 11:30 UTC (in summer) / 12:30 UTC (in winter),
both safely past Triton's 11:00 UTC cut-off.

**Heads up on `Last day` semantics:** Triton's streaming data finalizes a
few days behind real time. When you click `Last day` mid-week, you may see
the report resolve to a date 2–4 days ago — that's not a bug, it's Triton's
data-finalization lag. Pick `Last day` anyway and let the scheduled email
send whatever Triton considers freshest each morning. The loader's
`ON CONFLICT DO UPDATE` makes repeat sends of the same date a safe no-op.

### Q2a — Daily Cume

> One row per (station × day). 4 rows per day.

| Item | Value |
|---|---|
| **Saved query name** | `[WMS-Q2A-CUME-DAILY] Daily Cume (all 4 stations)` |
| **Stations** | WYMSFM, WYMSHD2, 414 Music, Rhythm Lab Radio 24/7 |
| **Dimensions** | Station, Day |
| **Metrics** | AAS, TLH, CUME, SS, TSL |
| **Date range** | `Last day` (the highlighted default preset) |
| **Schedule interval** | Daily |
| **Schedule time** | 07:00 Central Time |
| **Target table in Neon** | `wms.fact_daily_cume` |

### Q2b — Weekly Cume

> One row per (station × week). 4 rows per week, every Monday.

| Item | Value |
|---|---|
| **Saved query name** | `[WMS-Q2B-CUME-WEEKLY] Weekly Cume (all 4 stations)` |
| **Stations** | WYMSFM, WYMSHD2, 414 Music, Rhythm Lab Radio 24/7 |
| **Dimensions** | Station, Week |
| **Metrics** | AAS, TLH, CUME, SS, TSL |
| **Date range** | `Last week` (the rolling-week preset) |
| **Schedule interval** | Weekly |
| **Day of week** | Monday |
| **Schedule time** | 07:30 Central Time |
| **Target table in Neon** | `wms.fact_weekly_cume` |

### Q2c — Monthly Cume

> One row per (station × month). 4 rows on the 1st of each month.

| Item | Value |
|---|---|
| **Saved query name** | `[WMS-Q2C-CUME-MONTHLY] Monthly Cume (all 4 stations)` |
| **Stations** | WYMSFM, WYMSHD2, 414 Music, Rhythm Lab Radio 24/7 |
| **Dimensions** | Station, Month |
| **Metrics** | AAS, TLH, CUME, SS, TSL |
| **Date range** | `Last month` |
| **Schedule interval** | Monthly |
| **Day of month** | 1 |
| **Schedule time** | 08:30 Central Time |
| **Target table in Neon** | `wms.fact_monthly_cume` |

### Q3 — Monthly Geography

> Rolled up by DMA (Designated Market Area) and city. ~800 rows per month.

| Item | Value |
|---|---|
| **Saved query name** | `[WMS-Q3-GEO] Monthly Geography by DMA + City` |
| **Stations** | WYMSFM, WYMSHD2, 414 Music, Rhythm Lab Radio 24/7 |
| **Dimensions** | Station, Month, City, DMA |
| **Metrics** | AAS, TLH, CUME, SS, TSL |
| **Date range** | `Last month` |
| **Schedule interval** | Monthly |
| **Day of month** | 1 |
| **Schedule time** | 09:00 Central Time |
| **Target table in Neon** | `wms.fact_monthly_geo` |

**Heads up:** if Triton splits "City" and "DMA" into separate dimension
toggles, enable both. The export must contain a column literally named
`City` and one literally named `DMA` — the loader looks for those exact
header strings.

### Q4 — Monthly Device

> Device family + concrete device + player breakdown. ~50–200 rows per
> month depending on listener mix.

| Item | Value |
|---|---|
| **Saved query name** | `[WMS-Q4-DEVICE] Monthly Device + Player` |
| **Stations** | WYMSFM, WYMSHD2, 414 Music, Rhythm Lab Radio 24/7 |
| **Dimensions** | Station, Month, Device family, Device, Player |
| **Metrics** | AAS, TLH, CUME, SS, TSL |
| **Date range** | `Last month` |
| **Schedule interval** | Monthly |
| **Day of month** | 1 |
| **Schedule time** | 09:30 Central Time |
| **Target table in Neon** | `wms.fact_monthly_device` |

---

## After all 6 are scheduled — verify the chain

You don't actually have to wait until the next morning. Triton lets you
**run a saved query manually** from the Saved Queries list — it doesn't
trigger the scheduled-email path, though, so for end-to-end testing the
honest answer is: **wait for one real run**.

When the next scheduled time fires, here's how to confirm each link in
the chain is alive.

### 1. Did Triton actually send the email?

Check AgentMail's inbox at `triton-ingest@agentmail.to`. You should see a
message from `noreply@tritondigital.com` with the query name (including the
`[WMS-...]` tag) in the subject, and an XLSX attached.

### 2. Did Fly.io receive and process it?

```bash
flyctl logs --app rm-data-loader
```

You're looking for a line like:

```
INFO rm-data-loader loaded [WMS-Q1-HOURLY]:
  {'query': 'Q1 Hourly', 'table': 'wms.fact_hourly_listening',
   'rows_read': 96, 'rows_upserted': 96, 'elapsed_sec': 0.3}
```

That single log line confirms: signature verified ✓, XLSX downloaded ✓,
loader ran ✓, rows written ✓.

### 3. Did Neon actually grow?

Connect to Neon (Hex, psql, the Neon SQL editor — any of them) and run:

```sql
SELECT MAX(date), COUNT(*)
FROM wms.fact_hourly_listening;
```

`MAX(date)` should be yesterday (or whatever date Triton just sent).
`COUNT(*)` should be 96 more rows than yesterday (4 stations × 24 hours).

### 4. Did Slack tell you about it?

If `SLACK_WEBHOOK_URL` is set as a Fly secret, you'll see a
`:white_check_mark: *[WMS-Q1-HOURLY]* upserted N rows ...` in whatever
channel that webhook points at. If you DON'T see Slack messages, run
`flyctl secrets list --app rm-data-loader` — if `SLACK_WEBHOOK_URL` isn't
in the list, the service is intentionally silent (Slack is optional).

---

## Troubleshooting

### "The email arrived in AgentMail but nothing happened in Neon."

Most common cause: the subject doesn't contain a recognized tag. Check:

- Does the email subject contain the literal text `[WMS-Q1-HOURLY]` (or
  the appropriate tag)? Brackets included, all caps.
- If the subject is the human label only (no brackets), your query name
  doesn't have the tag — go back to Triton and rename the saved query.

The router treats unknown tags as "ignore" and returns HTTP 200, so the
email won't bounce — it'll just silently do nothing. Look at Fly logs:

```bash
flyctl logs --app rm-data-loader | grep "no route"
```

### "Fly logs say signature verification failed."

The `AGENTMAIL_WEBHOOK_SECRET` on Fly doesn't match the one AgentMail is
signing with. Re-run:

```bash
python jobs/register_agentmail_webhook.py
flyctl secrets set AGENTMAIL_WEBHOOK_SECRET=whsec_... --app rm-data-loader
```

Then redeploy automatically restarts the machines.

### "Fly logs say 'no XLSX attachment'."

Triton sent a CSV or PDF instead of XLSX. In the schedule form, the format
toggle has to be XLSX. Edit the schedule and reselect.

### "DB row count didn't change."

Two possibilities:

1. The email never arrived → check AgentMail inbox first.
2. The email arrived with the same data Triton sent last time (same
   `station + date + hour`) → the loader's `ON CONFLICT DO UPDATE` makes
   re-uploads a no-op for the row count. Run:
   ```sql
   SELECT MAX(loaded_at) FROM wms.fact_hourly_listening;
   ```
   If `loaded_at` is recent, the loader DID run — the data just hadn't
   changed.

### "Data looks wrong / missing the most recent day."

Triton needs time for data to finalize. We schedule everything **after
11:00 UTC** for exactly this reason. If your morning email is light, check
the timezone — Triton's schedule must be set to **Central Time**, not the
browser's local time.

### "I hit Triton's 30-schedule limit."

We only need 6. If you see this error, you probably have old test
schedules sitting around. Open the Saved Queries list and delete any
schedules that aren't in this doc.

### "The Q3 / Q4 export has different column names than expected."

The loaders match column headers exactly. If Triton changes a label
(e.g. "DMA" becomes "Designated Market Area"), the loader will fail with
a clear error like:

```
[Q3 Monthly Geography] export is missing expected columns ['DMA']
```

Fix is in `loaders/load_q3_monthly_geo.py` — update the `EXPECTED_COLS`
list. Re-deploy.

---

## Setup checklist (cross off as you go)

- [ ] Verified `curl https://rm-data-loader.fly.dev/health` returns 200
- [ ] Verified `AGENTMAIL_WEBHOOK_SECRET` is `Deployed` on Fly
- [ ] Sent a test email to `triton-ingest@agentmail.to` and confirmed it
      lands in AgentMail
- [ ] Whitelisted `noreply@tritondigital.com` in AgentMail (if filtering)
- [ ] Q1 — saved as `[WMS-Q1-HOURLY] Hourly Listening (all 4 stations)` +
      scheduled Daily 06:30 CT
- [ ] Q2a — saved as `[WMS-Q2A-CUME-DAILY] Daily Cume (all 4 stations)` +
      scheduled Daily 07:00 CT
- [ ] Q2b — saved as `[WMS-Q2B-CUME-WEEKLY] Weekly Cume (all 4 stations)`
      + scheduled Weekly Monday 07:30 CT
- [ ] Q2c — saved as `[WMS-Q2C-CUME-MONTHLY] Monthly Cume (all 4 stations)`
      + scheduled Monthly Day 1 08:30 CT
- [ ] Q3 — saved as `[WMS-Q3-GEO] Monthly Geography by DMA + City` +
      scheduled Monthly Day 1 09:00 CT
- [ ] Q4 — saved as `[WMS-Q4-DEVICE] Monthly Device + Player` +
      scheduled Monthly Day 1 09:30 CT
- [ ] First Q1 (or Q2a) run lands in Neon successfully — full chain green
- [ ] Slack `:white_check_mark:` posted (if Slack is wired)

---

## What this doc does NOT cover

- **Historical backfill** of Q1–Q4. That's already done (117,940 rows as
  of 2026-06-09). The backfill used a separate set of "Bulk" saved queries
  with fixed date ranges, run manually from your laptop via
  `loaders/load_q*.py`. Don't confuse the two — bulk queries are
  one-and-done, scheduled queries run forever.

- **Non-Triton sources** (Funraise, Meta, GA, Email ESP, Finance). Those
  are Phases 9–11. Different setup pattern (Coupler.io or vendor webhook,
  not AgentMail).

- **Editing the loaders.** If Triton's column headers change, you'll need
  to update `loaders/load_q*.py`. That's a separate task — see the
  troubleshooting section above.

---

## Reference

- **Triton's official docs:** https://help.tritondigital.com/docs/saving-and-scheduling-queries
- **Webhook router code:** `service/router.py` (the tag regex lives here)
- **Loader code:** `loaders/load_q*.py` (one per query)
- **Schema reference:** `CLAUDE.md` → "Query catalog (streaming)"
