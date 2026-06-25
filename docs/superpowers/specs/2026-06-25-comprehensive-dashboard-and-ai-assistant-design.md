# Comprehensive Audience Dashboard + AI Data Assistant — Design

- **Date:** 2026-06-25
- **Status:** Approved (brainstorm) → ready for implementation planning
- **Author:** Tarik Moody + Claude (brainstorming session)

## Goal

Make the RM Executive Dashboard (a) comprehensive for every leadership audience
(role-based views, including the Board), and (b) able to answer questions that go
*beyond what's displayed* through a trustworthy "chat with your data" assistant.

The dashboard today surfaces ~17 curated aggregates out of a warehouse with 30+
tables across 8 domains. You can't pre-build a tab for every question a board
member or director will ask. A conversational layer closes that gap — but only if
it is **accurate enough to put in front of a board**, where a confidently-wrong
number is worse than no answer.

## Locked decisions (from the brainstorm)

| Decision | Choice |
|---|---|
| Scope | **One combined spec**, delivered in phases (foundation → tabs → assistant) |
| Data access | **Hybrid**: semantic metrics first, guarded read-only SQL fallback |
| Assistant power | **Level 1**: answer + charts in the panel; reads dashboard context; does **not** drive the UI |
| Access control | **Single shared passcode** (gates UI *and* runtime); SSO is a later phase |
| Runtime | **Vite dashboard + thin Node CopilotKit runtime (Claude)**; data logic stays in Python |
| Model | **Claude Sonnet 4.6** default; Opus escalation optional; configurable |
| Audiences | **7 role views**: Board, Program Director, Development, Digital, Social, Underwriting, Finance/Exec |

## The load-bearing idea

**One semantic layer feeds both the dashboard tabs and the assistant.**
`semantic/rm_metrics.yml` stops being a Hex-only artifact and becomes the canonical
metric registry that a FastAPI metric service executes. Static tabs render those
metrics; the assistant calls the *same* metrics as tools. A chart and a chat answer
can never disagree, because they resolve to the same definition of "revenue,"
"AQH share," etc. This is what makes a combined spec coherent rather than two
bolted-together things.

## Architecture

```
            ┌──────────────────── Vite + React dashboard ────────────────────┐
            │  Role tabs (Board/PD/Dev/Digital/Social/Underwriting/Finance)   │
            │  + global Brand/Period filters (already built)                  │
            │  + <CopilotChat> side panel  ──/api/copilotkit──┐               │
            │  + useCopilotReadable(active tab, brand, period)│               │
            └──────────────────────────────────────────────────┼─────────────┘
                                                                ▼
                                              Node CopilotKit runtime (Claude)
                                                tools: ask_metric, ask_sql
                                                (thin — proxies to FastAPI)
                                                                │ HTTP
                                                                ▼
              FastAPI (Python)  ── metric service (runs registry / rm_metrics.yml)
                                ── guarded /api/ask-sql (read-only Neon role)
                                                                │
                                                                ▼
                                                              Neon
```

Components communicate over HTTP with well-defined contracts. The Node runtime holds
**no data logic** — it orchestrates the agent and proxies tool calls to FastAPI, so
metric correctness lives in exactly one language next to the warehouse.

## Phasing

Each phase ships and is QA'd independently.

### Phase 0 — Semantic foundation (de-risks everything)

1. **Metric registry** (`metrics/registry.py`) — the executable form of
   `rm_metrics.yml`. Each metric: `id`, plain-English `name`/`description`, `unit`,
   `source` (origin table), allowed `params` (brand, period, group_by), and a
   **query builder** that emits correct parameterized SQL. Encodes the footgun rules:
   revenue = `status='Complete'` only; cume is non-additive; `stg_` vs empty `fact_`;
   Nielsen ≠ streaming; brand mapping (RM88+RMORG → "Radio Milwaukee").
   - The YAML remains the human-readable spec + the assistant's tool catalog.
   - A test asserts registry and YAML do not drift.
2. **Metric service** (`GET /api/metric/{id}?brand=&period=&group_by=`) — validates
   params, runs the builder, returns `{ data, meta: {name, description, source, unit} }`.
   Consumed by **both** the dashboard tabs and the assistant's `ask_metric` tool.
   `brand` accepts the existing brand keys (`RM`, `HYFIN`, `RM414`, `RLR`, `GWML`,
   or `ALL`); `period` reuses the existing front-end presets (`30d`, `90d`, `12m`,
   `ytd`, `all`) so the tabs, filters, and assistant share one vocabulary.
3. **Read-only safety layer** — a dedicated read-only Neon role (`SELECT` on an
   allowlist of schemas; **revoked** on donor-detail tables; `statement_timeout` +
   row cap). Connection string stored as `DATABASE_URL_RO`.
4. **Refactor** the existing ~17 ad-hoc queries in `dashboard_api.py` to flow through
   the metric registry where they map. (Real work; it is what collapses two sources
   of truth into one.)

### Phase 1 — Role audience tabs ("comprehensive for different audiences")

Built on the metric service + the brand/period filters already shipped. Per-tab
widget specs already exist in `docs/dashboard-roadmap.md`; this phase binds them to
the metric service and adds:

- **Board tab (new landing view)** — org-wide health narrative in plain English:
  total reach (broadcast cume + streaming + web + social), revenue vs budget +
  surplus + sustainer MRR, donor health (active / retention / sustainers), Nielsen
  market position. Heaviest editorial, lightest jargon. Built for volunteer board
  members, not analysts.
- **Editorial layer** — a `deck` (one-sentence "what + why") and `info` (ⓘ tooltip)
  prop on `ChartCard`/`Kpi`, plus a shared `glossary.js` in RM voice (glossary +
  section intros drafted in `docs/dashboard-roadmap.md`). **The same glossary text
  seeds the assistant's system prompt** — tooltips and chat speak with one voice.
- **Tab reorganization** — current 6 source tabs map onto the 7 role tabs
  (Overview→Board; Financial→Finance/Exec; Digital Reach→Digital; Social stays;
  Nielsen/Triton feed Program Director + Underwriting; Mailchimp folds into Digital).
  Reuses every existing component (`Kpi`, `ChartCard`, `BrandFilter`, badges, empty
  states).

Phase 1 ships and is QA'd with zero AI in the picture — board value on day one.

### Phase 2 — AI Data Assistant

- **Frontend (Vite)** — `@copilotkit/react-core` + `@copilotkit/react-ui` render a
  `<CopilotChat>` side panel (the "Chat+" layout: dashboard left, assistant right),
  pointed at the Node runtime via `<CopilotKit runtimeUrl=...>`. A
  `useCopilotReadable` hook exposes the current dashboard context (active role tab,
  brand, period) so questions inherit the on-screen filters and the tone matches the
  tab (Board = plainest).
- **Node runtime** — Express + `CopilotRuntime` + a Claude agent. System prompt =
  RM-voice glossary + the metric catalog + rules: *answer through a metric first;
  cite the source; always render a chart, never a bare number; if nothing fits, say
  so; never expose row-level donor data.*
- **Two tools (proxy to FastAPI):**
  - `ask_metric(id, brand, period, group_by)` → `/api/metric/...` — default,
    correct-by-construction.
  - `ask_sql(sql)` → guarded `/api/ask-sql` — only when no metric covers the
    question. FastAPI validates (single `SELECT`, table allowlist, injected
    `LIMIT`/timeout) and runs on the read-only role.
- **Generative UI** — a render-only `useCopilotAction` draws results with the
  **dashboard's own Recharts components** (brand colors, formatters), so a chat chart
  is visually indistinguishable from a tab chart. Each answer = plain-English summary
  + chart + `(source: …)` citation.
- **Model** — Claude Sonnet 4.6 default (cost/latency); Opus escalation for hard
  multi-step questions; configurable via runtime env.

#### End-to-end traces

```
"HYFIN reach last 90 days?"
  → ask_metric(ig_reach, brand=HYFIN, period=90d)
  → chart + "Up 12% vs prior 90d (source: IG reach metric)"

"Which ZIPs do sustainers cluster in?"
  → no metric → ask_sql(SELECT postal_code, count(*) ... GROUP BY 1 ORDER BY 2 DESC LIMIT 50)
  → bar chart + "(computed via read-only SQL)"
```

## Security (the trust contract)

- **Passcode gates BOTH the UI and the Node runtime.** If only the React app checks
  the passcode, the LLM/SQL endpoint is still public. The runtime requires the same
  token on every request. Non-negotiable.
- **Read-only Neon role** — `SELECT` on an allowlist of schemas; revoked on
  donor-detail tables; `statement_timeout` + row cap.
- **Assistant contract** — answer through a metric or guarded SQL, **cite or refuse**;
  never a bare number; never row-level PII. Donor data reaches the assistant **only
  as aggregates** (via metrics), never as rows.

## Testing (what makes it board-safe)

- **Metric golden tests** — each metric compared to a known-good value, and to the
  current dashboard number during the refactor (catches drift).
- **Registry ↔ YAML sync test.**
- **Guardrail tests** — `ask_sql` rejects writes/DDL/multi-statement/off-allowlist;
  enforces `LIMIT`/timeout; PII tables blocked.
- **Assistant eval set** — ~25 representative questions (Board + each role) with
  expected behavior (which metric, SQL, or graceful refusal), run as a regression
  eval. This is the key trust artifact: it's how a model/prompt change is caught
  before it produces wrong numbers.
- **Frontend** — build + browser QA pass (same approach used for the brand-filter work).

## Cost control

Sonnet default; max-output budget + rate limit per request; passcode keeps it
non-public; all assistant queries logged for spend visibility (even without per-user
identity).

## Out of scope (named to prevent scope creep)

- Google Workspace SSO / per-user audit (later phase; passcode now).
- Agent **driving** the UI (setting filters, opening tabs).
- Co-creator **canvas** (building/pinning new custom views).
- Paid social (`meta_ads`), and any source not already loaded.

## Risks / watch-items

- **Metric registry build cost** — a parameterized metric layer is the bulk of
  Phase 0. Mitigated by keeping the registry small (start with the ~13 metrics in
  `rm_metrics.yml`) and adding metrics as questions demand.
- **SQL-fallback accuracy** — guarded SQL can still produce a logically-wrong answer
  even when it runs safely. Mitigated by: prefer metrics, cite "computed via SQL"
  (lower-confidence signal), and the eval set.
- **CopilotKit v2 API churn** — confirm the exact runtime/adapter syntax (Anthropic
  adapter, `createCopilotExpressHandler`) against current docs at build time.
- **Two new services to operate** (Node runtime + read-only role) — small, but new
  surface to deploy, secret, and monitor.

## Component / file inventory (for planning)

- `metrics/registry.py` (new) — metric definitions + query builders.
- `service/metric_api.py` (new) — `/api/metric/{id}` endpoint.
- `service/ask_sql_api.py` (new) — guarded `/api/ask-sql` endpoint + validator.
- `schema/016_readonly_role.sql` (new — next migration number after `015`) — read-only Neon role + grants.
- `dashboard/src/tabs/*` (refactor) — 7 role tabs on the metric service.
- `dashboard/src/glossary.js` (new) — RM-voice definitions (shared with assistant).
- `dashboard/src/assistant/*` (new) — CopilotKit panel + readable context + chart action.
- `runtime/` (new Node service) — Express + CopilotRuntime + Claude agent + tools.
- `tests/` — metric golden tests, registry/YAML sync, guardrail tests, assistant eval set.
