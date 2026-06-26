# Radio Milwaukee Data Warehouse — What's In It

*A plain-English snapshot for the leadership team.*
*Last updated: June 24, 2026.*

## The big picture

We now have **one central database** that pulls together audience and engagement
data from across the organization — streaming, website, social media, and email
— and keeps it in a single place so we can finally answer questions across
channels instead of logging into six different dashboards.

- **Size:** ~328 MB
- **Records:** nearly **2 million rows** of real data
- **Sources live today:** 4 (Streaming, Website, Social, Email)
- **Brands covered:** 88Nine (RM88), HYFIN, Grace Weber's Music Lab (GWML),
  plus the flagship Radio Milwaukee accounts — all tagged so any number can be
  sliced by brand
- **Refresh:** updates automatically (daily for most sources)

Everything below is already loaded and queryable. It feeds our dashboards in
Hex, which leadership and department directors can read without touching SQL.

---

## What's in the database today

| Data source | What it tells us | Records | History | How it arrives |
|---|---|---|---|---|
| **Streaming** (Triton) | Who's listening to our streams — by hour, day, week, month; cume, time spent listening, geography, device | **~121,000** | Jan 2024 → present | Daily email → auto-load |
| **Website** (Google Analytics) | Site traffic — sessions, users, pages, cities, devices, events, hourly patterns | **~1.82 million** | Feb 2022 → present | Daily auto-pull |
| **Social** (Facebook + Instagram, organic) | Page/profile reach, followers, and per-post performance | **~7,800** | 2024/2025 → present | Daily auto-pull |
| **Email** (Mailchimp) | Every newsletter sent, opens/clicks/unsubscribes, audience size, list growth | **~880** | varies (list growth back to 2014) | Daily auto-pull |
| **Reference data** | Calendar, the 6 brand/station definitions, channel mapping | ~4,000 | — | Maintained in-house |

### In plain terms, what each source answers

**Streaming** — "How many people are listening, for how long, from where, and on
what device?" Hourly detail back to January 2024, covering all four streams.
*(Note: this is **streaming only** — over-air radio ratings come from Nielsen,
which is still to do.)*

**Website** — "How many people visit radiomilwaukee.org and the HYFIN site, what
do they read, where are they, and what do they click?" This is the largest
dataset by far (~1.8M rows) and goes back to early 2022.

**Social** — "What's our organic reach and follower growth on Facebook and
Instagram, and which posts performed best?" Per-post detail plus monthly trend
lines per brand. *(Paid/advertising social is a future add.)*

**Email** — "How is each newsletter performing?" We have **573 individual
campaigns** with subject lines, opens, clicks, unsubscribes, and bounces, broken
out by list (Radio Milwaukee 457, HYFIN 92, GWML 24), plus current audience size
(~18,400 RM / ~2,400 HYFIN / ~1,100 GWML) and list-growth history back to 2014.

---

## By the numbers

| Area | Rows |
|---|---:|
| Website (Google Analytics) | 1,824,019 |
| Streaming (Triton) | 120,775 |
| Social (Facebook + Instagram) | 7,773 |
| Email (Mailchimp) | 880 |
| Reference / brand definitions | 4,042 |
| **Total** | **~1,957,000** |

---

## What we still need to add

These are designed and have a reserved home in the database — they just need
data wired in.

| Source | What it adds | Why it matters | Status |
|---|---|---|---|
| **Nielsen** | Over-air radio ratings (broadcast cume/AQH for 88Nine FM and HYFIN HD2) | Completes the audience picture — today we measure streaming, but not the much larger over-air audience | **To do** |
| **Funraise** | Donations and membership — every gift, donor records, recurring giving | Ties audience behavior to giving; powers development and grant reporting | **To do** (schema designed; needs API/webhook hookup) |
| **Finance** | Revenue actuals, budget, and expenses by month and category | Lets us compare revenue vs. budget and see the full multi-source revenue mix in one place | **To do** |

Once these three are in, a single monthly view can show **audience → engagement
→ giving → revenue vs. budget** across the whole organization.

---

## Next version (later in 2026): Marketron

**What it is:** Marketron is our advertising/underwriting traffic and revenue
system — it holds the orders, the spots that aired, and the billing. It's the
missing piece for the *earned-revenue* side of the story (the underwriting and
sponsorship dollars), and it has a reserved home in the database already (the
`underwriting` and `finance` areas).

**Why we want it:** combined with everything above, Marketron would let us answer
questions like *"which dayparts and shows are sold out vs. have inventory to
sell,"* *"how does underwriting revenue track against budget,"* and *"what did a
sponsor actually receive in delivered impressions."*

**How we'd get it in — options to confirm with our Marketron rep (in priority
order):**

1. **Scheduled report exports (most likely / fastest).** Marketron can generate
   reports (orders, as-run logs, billing) and deliver them on a schedule by email
   or SFTP. We already do exactly this for Triton streaming data — an emailed file
   auto-loads into the warehouse — so we'd reuse that proven pattern.
2. **Marketron API.** Marketron's NXT platform exposes APIs for orders/traffic
   data. Access usually requires credentials and may depend on our product tier
   and contract — worth asking what's included in our agreement.
3. **Direct data feed / nightly file drop.** Some Marketron deployments support a
   recurring data export to a secure location, which we'd pick up automatically.

**Recommended path:** start by asking our Marketron account rep two questions —
(a) "Can we schedule recurring exports of orders, as-run, and billing to email or
SFTP?" and (b) "Is API access to that data included in our contract?" The answers
decide whether we use the same email-loader pattern as Triton or build an API
connection. Target: **next version, later in 2026.**

---

## How it stays current (and what it costs)

- **Streaming and donations** arrive by automated email/webhook as they happen.
- **Website, social, and email** refresh automatically every day through a single
  ingestion tool (Coupler.io).
- **Dashboards** in Hex read straight from the warehouse, so they're always current.

The only paid tool is the daily ingestion service (~\$65/month, and we qualify for
nonprofit rates that bring our all-in tooling well under \$1,000/year). The
database and dashboard tools run on free/low tiers today and scale with use.

---

## One-line summary for the board

> *We've built a single, automatically-updating data warehouse holding nearly
> 2 million records across streaming, web, social, and email — all tagged by
> brand. Nielsen ratings, donations (Funraise), and finance are next, with
> advertising/underwriting data (Marketron) targeted for a later-2026 release.*
