# Phase 2 — CopilotKit "chat with your data" assistant — Design (MOO-177)

> The trustworthy in-dashboard AI analyst. v1 = read-only Q&A with citations, grounded in
> the metric registry + guarded SQL + the live dashboard view. Built on the Phase-0 foundation
> (metric API MOO-172/175, read-only `ask-sql` MOO-173) and the Phase-1 dashboard (MOO-176).

## Goal

Give every Radio Milwaukee leader an in-dashboard assistant that turns the warehouse into
decisions — answers questions in plain English, **always grounded in real data and cited**,
in the voice of the org's data analyst. It must never fabricate a number and never leak donor PII.

## Decisions (settled in brainstorming)

- **Architecture = Pattern A.** A `CopilotRuntime` hosted in a **Vercel serverless function**
  (`/api/copilotkit`) inside the existing `dashboard/` Vercel project, using the **Anthropic
  (Claude) adapter**, with server-side tools that HTTP-call the already-live Fly endpoints.
  Chosen over a Python AG-UI agent for least new infra, fastest path, and reuse of the guarded
  endpoints; we can swap in a Python AG-UI agent later without touching the frontend.
- **v1 scope = trustworthy read-only Q&A + citations.** No agentic UI control and no generative
  UI yet (both are later phases).
- **LLM = Claude** (latest appropriate model; `ANTHROPIC_API_KEY` server-side).

## Architecture

```
 dashboard/ (Vite SPA on Vercel)
 ├─ <CopilotKit runtimeUrl="/api/copilotkit"> + <CopilotSidebar>
 │     useCopilotReadable → exposes current tab, brand, range, visible KPIs
 │
 └─ /api/copilotkit  (Vercel Node serverless function)
        CopilotRuntime + AnthropicAdapter(model=claude-…)
        instructions = finalized system prompt (analyst role + warehouse grounding + trust rules)
        actions (server-side tools) ──HTTP──▶  rm-data-loader.fly.dev
          • get_metric   → GET  /api/metric/{id}?brand=&period=&group_by=
          • list_metrics → GET  /api/metrics            (catalog; NEW small endpoint)
          • query_sql    → POST /api/ask-sql            (guarded, rm_readonly, funraise blocked)
          • get_schema   → GET  /api/schema             (allowlisted tables/cols; NEW small endpoint)
```

The runtime sits behind the same Vercel project (and the same future auth) as the dashboard.
Tools are thin wrappers over endpoints we already trust; no new data path into Neon is created.

## The agent's tools (contracts)

- **`get_metric(id, brand?, period?, group_by?)`** → `{value, meta:{name, description, source, unit}}`.
  The curated path; prefer it. 12 metrics live: `streaming_tlh`, `avg_active_sessions`,
  `sustainer_mrr`, `active_donors`, `active_sustainers`, `total_donors`, `revenue`,
  `donor_retention_pct`, `lapsed_donors`, `new_donors`, `avg_gift`, `sustainer_share`.
- **`list_metrics()`** → the catalog (id, name, description, unit, source) so the agent knows
  what curated metrics exist before reaching for SQL. *(Backend: add `/api/metrics` listing the
  registry; trivial — the registry already holds this metadata.)*
- **`query_sql(sql)`** → bounded rows. Single `SELECT`/`WITH` only; validator + outer LIMIT;
  runs as `rm_readonly` (SELECT allowlist, **`funraise` schema blocked**, 15s timeout). Already live.
- **`get_schema()`** → the allowlisted tables + columns (+ one-line descriptions) the agent may
  query, so it writes valid SQL instead of guessing. *(Backend: add `/api/schema` derived from the
  `rm_readonly` allowlist + `information_schema`; or a static catalog from `semantic/rm_metrics.yml`.)*

## System prompt

Source: `radio-milwaukee-data-analyst-system-prompt.md` (Tarik's). It already encodes the trust
model (BLUF, insight-not-data-dump, cite source + window, never fabricate, aggregate-by-default,
right-size confidence on small Nielsen samples, plain language, BLUF tone). It has two `[FILL IN]`
sections, completed below with the real warehouse state and stored in-repo for the runtime to load
(e.g. `dashboard/api/system-prompt.md`).

**Data sources & access (fills §"Data sources and access"):** the agent retrieves figures ONLY via
the four tools above. What the warehouse holds today (grain · coverage):
- Streaming (Triton, `wms.*`): TLH / avg active sessions / cume / TSL, 4 brands, hourly→monthly, Jan 2024– (RLR Nov 2025–).
- Broadcast (Nielsen, `nielsen.fact_vital_signs`): AQH persons & share, weekly/daily cume, TSL; RM88 & HYFIN; books ~mid-2025–. Small-sample caution.
- Membership (Funraise, `funraise.*`): 2023–; **aggregates only** (see access).
- Web (GA4 `ga.stg_*`), Social (Meta `meta_organic.*`, incl. daily IG followers), Email (Mailchimp `email_esp.stg_*`), App (AppFigures).
- Finance (`finance.*`): revenue vs budget, revenue mix — **only ~Feb–Apr 2026 loaded**; hedge on longer finance trends.
- **Not yet loaded** (answer "not tracked yet"): underwriting contracts/pipeline/sponsors (only underwriting *revenue* exists as a finance category), events ticketing, grants pipeline, podcast downloads.

**Access rules (fills §"Access rules"):** individual donor records / giving histories / emails are
**not reachable** — `query_sql` is blocked from `funraise` by the DB role; donor figures come only as
aggregates via `get_metric`. If asked for an individual or named gift, say individual-level detail
isn't available through the assistant and offer the aggregate.

## Trust & citation model (the point of the feature)

- **Tool-only numbers** — the prompt forbids inventing figures; the tools are the only number source.
- **Registry-first** — prefer `get_metric` so the chat and the dashboard never disagree; `query_sql`
  is the long-tail fallback.
- **Citations** — every figure names its metric/source + time window (registry returns `source`;
  surface the metric id / the SQL run). Render tool calls so the user can see the provenance.
- **PII enforced at the data layer**, not just by instruction (the `funraise` block).
- **Schema-grounded SQL** via `get_schema` so `query_sql` is valid and stays on allowlisted tables.

## Frontend integration

- Add `@copilotkit/react-core` + `@copilotkit/react-ui` (this phase intentionally adds npm deps).
- `<CopilotKit runtimeUrl="/api/copilotkit">` wraps `App`; `<CopilotSidebar>` (collapsible) as the chat surface.
- `useCopilotReadable` exposes the live view (active tab, brand, range, and the visible KPI/payload
  summary) so "what am I looking at / why did this move?" is grounded in the current screen.
- Voice/labels reuse `glossary.js` so the assistant and the dashboard speak identically.

## Deploy shape

- Frontend + `/api/copilotkit` deploy together on the existing Vercel `dashboard` project.
- New secret: `ANTHROPIC_API_KEY` (Vercel env, server-side only).
- Backend additions (`/api/metrics`, `/api/schema`) deploy on Fly (`rm-data-loader`) — small, additive.

## Testing

- Tool wrappers: unit-test each calls the right Fly endpoint + shapes the result.
- Trust harness: a fixture set of questions asserting (a) numbers match `get_metric`/dashboard,
  (b) a donor-PII request is refused, (c) an unanswerable question yields "not tracked yet" not a
  fabricated number, (d) answers cite a source.
- Frontend build clean; manual chat QA against prod data.

## Out of scope (v1)

- Agentic UI control (navigate tabs / set filters via `useCopilotAction`) — Phase 2.5.
- Generative UI (agent renders inline charts) — later.
- Conversation memory/history persistence, multi-agent, a Python AG-UI agent.
- Write access of any kind.

## Open decisions / risks

- **Claude model tier** (Opus vs Sonnet) — cost vs depth; default Sonnet for chat latency, escalate if needed.
- **Auth** — the dashboard + `/api/copilotkit` are currently public; gate behind Vercel auth before sharing (tracked separately).
- **`get_schema` source** — generate from the `rm_readonly` allowlist (accurate, live) vs a static catalog (simpler). Lean live.
- **Rate/cost controls** — cap tokens / requests on the runtime; consider a per-session budget.
- **CopilotKit API specifics** — verify exact adapter/endpoint/action API against current docs at build (CopilotKit moves fast; this spec is grounded in the 2026-06 docs but the plan re-checks).

## Tracking

Branch `tarikjmoody/moo-177-copilotkit-assistant` off `main` (slices 1–3 merged + deployed).
MOO-177 (epic-level Phase 2). Plan: `docs/superpowers/plans/2026-06-26-phase2-copilotkit-assistant.md` (next).
