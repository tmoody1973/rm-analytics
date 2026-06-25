# Funraise 2023→2026 backfill — export plan (2-month windows)

> Goal: export every historical transaction from Jan 2023 → today out of Funraise,
> in chunks small enough to clear the **10,000-record export cap**, with **zero
> gaps** between chunks. 21 windows total.

## Why these exact dates (read this once)

Funraise's filter uses **two rules**: `Donation Date is after [X]` **and**
`Donation Date is before [Y]`. The danger is the boundary day: if `is after` and
`is before` both *exclude* their date, a gift dated exactly on a shared boundary
(e.g. Jan 1) gets missed by both the window before it and the window after it.

To make this **bulletproof regardless of how Funraise treats the edges**, every
window below uses:
- **`is after` = the last day of the month _before_ the window** (e.g. Dec 31 for a January start)
- **`is before` = the first day of the month _after_ the window** (e.g. Mar 1 for a February end)

This guarantees the first day of each window is always *strictly after* the
"after" date, and the last day is always *strictly before* the "before" date —
so no day is ever orphaned. Adjacent windows may overlap by a day at most, which
is **completely harmless**: the loader keys on `transaction_id` and de-duplicates,
so re-importing the same gift just overwrites itself. **When in doubt, overlap —
never gap.**

## Export settings (same for every window)

1. Set the two `Donation Date` filters to the window's **is after** / **is before** dates, click **Apply**.
2. **Check the `Transactions` count** shown at the top (like the `39,631` you saw).
   - If it's **≤ 9,500** → safe, export it.
   - If it's **> 9,500** → split that window (see "If a window is too big" below) before exporting.
3. Export as **CSV or XLSX**, including the columns from
   [`funraise-export-checklist`](./funraise-export-checklist.md) (gift fields +
   designation/fund, fee covered, refund status, channel, recurring link, donor
   city/state/ZIP, and **date + time**). Email/names handling is covered there.
4. Save the file with a clear name, e.g. `funraise_2023-01_2023-02.csv`, and drop
   the path in chat — I'll load it. Order doesn't matter; re-runs are safe.

## The 21 windows

Work top to bottom. Tick each box as you export it, and jot the count + filename.

| # | Window | `is after` | `is before` | Count seen | ☑ Exported | File saved |
|---|--------|-----------|------------|-----------|-----------|-----------|
| 1 | Jan–Feb 2023 | Dec 31, 2022 | Mar 1, 2023 | | ☐ | |
| 2 | Mar–Apr 2023 | Feb 28, 2023 | May 1, 2023 | | ☐ | |
| 3 | May–Jun 2023 | Apr 30, 2023 | Jul 1, 2023 | | ☐ | |
| 4 | Jul–Aug 2023 | Jun 30, 2023 | Sep 1, 2023 | | ☐ | |
| 5 | Sep–Oct 2023 | Aug 31, 2023 | Nov 1, 2023 | | ☐ | |
| 6 | Nov–Dec 2023 | Oct 31, 2023 | Jan 1, 2024 | | ☐ | |
| 7 | Jan–Feb 2024 | Dec 31, 2023 | Mar 1, 2024 | | ☐ | |
| 8 | Mar–Apr 2024 | Feb 29, 2024 | May 1, 2024 | | ☐ | |
| 9 | May–Jun 2024 | Apr 30, 2024 | Jul 1, 2024 | | ☐ | |
| 10 | Jul–Aug 2024 | Jun 30, 2024 | Sep 1, 2024 | | ☐ | |
| 11 | Sep–Oct 2024 | Aug 31, 2024 | Nov 1, 2024 | | ☐ | |
| 12 | Nov–Dec 2024 | Oct 31, 2024 | Jan 1, 2025 | | ☐ | |
| 13 | Jan–Feb 2025 | Dec 31, 2024 | Mar 1, 2025 | | ☐ | |
| 14 | Mar–Apr 2025 | Feb 28, 2025 | May 1, 2025 | | ☐ | |
| 15 | May–Jun 2025 | Apr 30, 2025 | Jul 1, 2025 | | ☐ | |
| 16 | Jul–Aug 2025 | Jun 30, 2025 | Sep 1, 2025 | | ☐ | |
| 17 | Sep–Oct 2025 | Aug 31, 2025 | Nov 1, 2025 | | ☐ | |
| 18 | Nov–Dec 2025 | Oct 31, 2025 | Jan 1, 2026 | | ☐ | |
| 19 | Jan–Feb 2026 | Dec 31, 2025 | Mar 1, 2026 | | ☐ | |
| 20 | Mar–Apr 2026 | Feb 28, 2026 | May 1, 2026 | | ☐ | |
| 21 | May–Jun 2026 | Apr 30, 2026 | Jul 1, 2026 | | ☐ | |

> Window 21 runs through "before Jul 1, 2026" — it captures everything up to
> today (2026-06-25); future dates simply have no data yet.

## If a window is too big (> ~9,500)

Split that 2-month window into its **two single months**, using the same
boundary rule. Example for a too-big **Sep–Oct 2025**:

| Sub-window | `is after` | `is before` |
|---|---|---|
| Sep 2025 | Aug 31, 2025 | Oct 1, 2025 |
| Oct 2025 | Sep 30, 2025 | Nov 1, 2025 |

General rule for any single month:
- `is after` = **last day of the previous month**
- `is before` = **first day of the next month**

A single month (~3,000–4,000 gifts) will be well under the cap even during pledge
drives. If a single *month* somehow still exceeds 10k, split it in half by day
(e.g. `is after [last day of prior month]` / `is before [16th]`, then
`is after [15th]` / `is before [1st of next month]`).

## After exporting

- Drop each file path in chat as you go (or batch them) — I load them with the
  idempotent backfill loader, so any overlaps/re-runs are safe.
  - We reconcile the grand total against Funraise's own count (the full-range
    filter showed `39,631` for 2023 alone) to confirm nothing was missed.
