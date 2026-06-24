# Wiring up Meta (Facebook + Instagram) organic data

A step-by-step guide to finish the four Meta organic dataflows so Facebook and
Instagram numbers start flowing into Neon, the same way GA4 already does.

Last updated: June 2026.

## What this does and why

We pull **organic** (non-paid) Facebook and Instagram data — page/profile
performance and per-post stats — into the `meta_organic` schema in Neon. From
there, Hex reads the tables to build the social views, joining each page/profile
to its station through `dim.brand_channels`.

Paid ads (spend, ROAS) are a **separate** build that lands in `meta_ads`. This
guide is organic only.

## What's already done (via the Coupler MCP)

Four dataflows are created with their source report type, metrics, date range
(from 2024-01-01), and their Neon destination table all configured. They are
**not finished** — Coupler requires you to pick the actual Facebook Pages and
Instagram profiles in the wizard by hand (it won't let that be set through the
API). That's the one manual step below.

| Dataflow | Pulls | Writes to Neon table |
|---|---|---|
| Meta Organic – FB Page Daily | Daily Facebook page performance | `meta_organic.stg_fb_page_daily` |
| Meta Organic – FB Posts Lifetime | Per-post lifetime stats + post text/link | `meta_organic.stg_fb_post_lifetime` |
| Meta Organic – IG Profile Daily | Daily Instagram profile reach | `meta_organic.stg_ig_profile_daily` |
| Meta Organic – IG Posts | Per-post Instagram performance | `meta_organic.stg_ig_post_lifetime` |

All four write to the Neon `meta_organic` schema using the existing pooler
connection (destination credential, same one GA4 uses).

## Which brands to select in each wizard

- **Facebook pages:** 88Nine Radio Milwaukee and HYFIN. (Grace Weber's Music
  Lab has no Facebook page, so there's nothing to pick for GWML on the FB side.)
- **Instagram profiles:** 88Nine (radiomilwaukee), HYFIN (hyfin.mke), and
  Grace Weber's Music Lab (gwmusiclab) — all three.

These match the rows already seeded in `dim.brand_channels`, so the Hex join
will line up automatically.

## The steps (do this once per dataflow)

1. In Coupler.io, open the dataflow (for example
   "Meta Organic – FB Page Daily (RM/HYFIN/GWML) → Neon").
2. In the **source** step you'll see a field for **Pages** (Facebook) or
   **Profiles** (Instagram) flagged as required/empty. Select the brands listed
   above for that dataflow.
3. Leave everything else as configured (report type, metrics, dates).
4. Click **Save and Run**. This is what actually fires the export to Neon — the
   MCP can configure a dataflow, but only "Save and Run" (or a schedule) writes
   the data.
5. Wait for the run to finish (green/success). Check that rows landed:
   in Neon, `SELECT count(*) FROM meta_organic.stg_fb_page_daily;` (swap the
   table name for each dataflow).
6. Repeat for the other three dataflows.

## After the first successful run

1. **Schedule them** for daily auto-refresh — same steps as
   `docs/coupler-scheduling-setup.md` (Automatic data refresh → Daily →
   ~5:00 AM Central). Schedule each only after it has run once successfully.
2. **Build the Hex clean layer.** In the "Radio Milwaukee Data" Hex project,
   add SQL cells that read the `stg_*` tables and join to `dim.brand_channels`
   to attach `station_code`:
   - FB tables → join the page id column to
     `dim.brand_channels WHERE platform = 'fb_page'`
   - IG tables → join the profile id column to
     `dim.brand_channels WHERE platform = 'ig_profile'`
   We read `stg_*` directly in Hex (not a database view) because Coupler's
   "Replace" mode drops and recreates the staging table on every run, which
   would cascade-drop any DB view built on top of it.

## A note on Facebook metrics

Meta has deprecated the old "organic reach" and "organic impressions" page
metrics. We use the current equivalents instead:

- **Content views** (`page_media_view`) ≈ impressions
- **Unique content viewers** (`page_total_media_view_unique`) ≈ reach

plus page views, new followers, unfollows, lifetime followers, post
engagements, reactions, and CTA clicks. Instagram returns its own fixed metric
set per report, so there's nothing to choose there.
