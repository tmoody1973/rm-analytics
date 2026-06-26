# Sheets Sync — manually-maintained Google Sheets → Neon

A tiny Google Apps Script that pushes a manually-updated sheet into the Neon
warehouse via the `rm-data-loader` service. **No Coupler account slot** — it
reuses the same loader + Slack-alert plumbing as the Triton pipeline.

Currently wired: the **finance KPI dashboard** (first tab of the finance sheet) →
`finance.fact_kpi_monthly`. Nielsen will be added later (its export is more
involved).

## How it works

1. Whoever updates the finance sheet clicks **Radio Milwaukee → Sync finance to
   Neon** (a custom menu).
2. The script reads the first tab's *displayed* values and POSTs
   `{ "dataset": "finance_kpi", "rows": [...] }` to
   `https://rm-data-loader.fly.dev/webhook/sheet` with a shared-secret header.
3. The service authenticates the secret, calls `load_finance_sheet`, which
   **unpivots** the wide indicator×month grid into long
   `(month, indicator, value)` rows and upserts into `finance.fact_kpi_monthly`
   (idempotent — re-syncing the same months just updates them).
4. Slack gets a ✅/❌ like every other source.

## Setup (once)

**Service side (you / dev):**
1. Set a shared secret on the service:
   ```bash
   flyctl secrets set SHEET_SYNC_SECRET="$(openssl rand -hex 24)" --app rm-data-loader
   ```
   Keep the value — you'll paste it into the Apps Script below.
2. Deploy the service (the `/webhook/sheet` route ships with it).

**Sheet side (finance owner):**
1. Open the finance Google Sheet → **Extensions → Apps Script**.
2. Paste `Code.gs` from this folder. Save.
3. **Project Settings → Script properties**, add:
   - `ENDPOINT` = `https://rm-data-loader.fly.dev/webhook/sheet`
   - `SECRET` = the `SHEET_SYNC_SECRET` value from step 1
4. Reload the sheet. The **Radio Milwaukee** menu appears.

## Using it

- **Manual:** update the sheet, then **Radio Milwaukee → Sync finance to Neon**.
- **Automatic (optional):** Apps Script → **Triggers** → add a daily time-driven
  trigger for `syncFinance` so it pushes overnight without anyone clicking.

## Notes

- The script sends **displayed** values, so currency/percent/accounting formatting
  is parsed server-side (`load_finance_sheet._clean_number`): commas, `$`, `%`,
  and `(123)` accounting-negatives all handled; blanks are skipped.
- Finance numbers never go public — this is an authenticated push, not a
  "publish to web" CSV.
- To add another tabular sheet later, map its tab to a dataset and add a
  `DatasetSpec` in `loaders/load_sheet_sync.py`.
