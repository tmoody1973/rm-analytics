# Setting up automatic schedules in Coupler.io

A step-by-step guide to make the dataflows refresh on their own, so nobody
has to click "Save and Run" every day.

Last updated: June 2026.

## What this does and why

Right now each Coupler dataflow only updates when you manually open it and run
it. Scheduling flips that: Coupler runs the pull and writes to Neon on its own,
on whatever cadence you set. Once every dataflow is scheduled, the warehouse
stays current with zero manual work, and the Hex views update automatically
because they read straight from the tables Coupler refreshes.

You set this once per dataflow.

## Before you start

A dataflow should have **run successfully at least once** before you schedule
it (so you know the connection and the destination work). All seven of our GA4
dataflows have already run, so they're ready to schedule.

## The steps (per dataflow)

1. In Coupler.io, open the dataflow you want to schedule (for example
   "GA4 – Geography (RM + HYFIN) → Neon").
2. Find the **Automatic data refresh** setting. It's in the dataflow's
   settings, near the schedule/run area.
3. **Toggle it on.**
4. Set the **interval**. Choose **Daily** for our sources (more on cadence
   below).
5. Set the **time** of day and the **time zone**. Use **Central Time** and an
   early-morning slot (around **5:00 AM**) so fresh data is waiting before
   anyone opens Hex.
6. If the interval offers **days of the week**, leave all days selected for a
   daily refresh.
7. **Save.** Coupler will show the next scheduled run time. That's your
   confirmation it's set.

Repeat for each dataflow.

## What cadence to use

| Source | Suggested schedule | Why |
|---|---|---|
| All GA4 dataflows | Daily, ~5:00 AM CT | Web numbers don't need to be hourly-fresh |
| Meta (when added) | Daily | Same |
| Mailchimp (when added) | Daily | Campaign/list data changes slowly |

Coupler can go as frequent as every 15 minutes, but daily is the right call for
all of these. Don't over-schedule — it just burns refresh runs against your
plan limit for no benefit.

## The seven GA4 dataflows to schedule

- [ ] GA4 – Radio Milwaukee Sessions → Neon
- [ ] GA4 – Geography (RM + HYFIN) → Neon
- [ ] GA4 – Device (RM + HYFIN) → Neon
- [ ] GA4 – Pages (RM + HYFIN) → Neon
- [ ] GA4 – Events (RM + HYFIN) → Neon
- [ ] GA4 – Sessions Hourly (RM + HYFIN) → Neon
- [ ] GA4 – Events Hourly (RM + HYFIN) → Neon

## One thing to know about how it refreshes

These dataflows use **Replace** mode, so every scheduled run re-pulls the full
history and rewrites the whole table. That's intentional: it keeps the data
self-correcting (if Google revises a past day's numbers, the next run picks it
up). At our data size this is fine. The Hex views read these tables directly,
so they reflect each refresh automatically with nothing to re-run on our side.

## If something's off

- **The daily interval isn't available, or the minimum interval is limited** —
  that's a billing-plan limit. Daily is available on essentially every plan, so
  this shouldn't bite us.
- **Data refreshes at the wrong time** — check the time zone on the schedule; it
  must be Central Time, not the browser's default.
- **A scheduled run fails** — open the dataflow's run history and check the
  error. The usual suspect for the Neon destination is the connection; it should
  be using the pooler host credential (the one ending `-pooler…/neondb`).

## After all seven are scheduled

The website data keeps itself current. Next we add Meta and Mailchimp dataflows
and schedule them the same way, then connect everything in Hex for the full
organization-wide app.

---

Source: [Coupler.io flow settings](https://docs.coupler.io/functionality/flow-settings)
and [features & limits](https://docs.coupler.io/functionality/coupler.io-features-and-limits).
