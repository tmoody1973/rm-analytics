# Phase 2 — CopilotKit assistant Implementation Plan (MOO-177)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`. Spec: `docs/superpowers/specs/2026-06-26-phase2-copilotkit-assistant-design.md`.
>
> **Framework caveat (read first):** CopilotKit's API moves fast. The FIRST step of any CopilotKit task is to pull CURRENT docs via the `copilotkit-mcp` tools (search-docs / explore-docs) or Context7 (`/copilotkit/copilotkit`) and confirm exact names (adapter, runtime endpoint, action/tool shape, provider props) before writing code. Treat the code sketches below as structure, not gospel.

**Goal:** Ship v1 of the in-dashboard "chat with your data" assistant — trustworthy read-only Q&A with citations — on Pattern A (CopilotRuntime in a Vercel function + Claude Sonnet + tools calling the live Fly endpoints).

**Architecture:** Vite SPA (`dashboard/`, on Vercel) + `dashboard/api/copilotkit.ts` (Vercel Node serverless function) running `CopilotRuntime` + Anthropic adapter, with server-side actions that HTTP-call `rm-data-loader.fly.dev`. Model `claude-sonnet-4-6` via `ANTHROPIC_MODEL` env.

## Global Constraints

- **Trust is the product:** tool-only numbers, registry-first, cite source + window, funraise PII blocked at the DB layer, schema-grounded SQL. The system prompt enforces voice + behavior.
- **No write paths.** Every tool is read-only; `query_sql` stays on `rm_readonly`.
- **Reuse live endpoints** — `get_metric`/`query_sql` already exist; only add `/api/metrics` + `/api/schema`.
- **Secrets server-side only** — `ANTHROPIC_API_KEY` lives in the Vercel function env, never shipped to the browser.
- This phase **does** add npm deps (CopilotKit) — unlike Phase 1.

---

### Task 1: Backend support endpoints (`/api/metrics`, `/api/schema`)

**Files:** Modify `service/main.py` (routes) and/or `service/metric_api.py`; maybe `service/schema_api.py` (new). Test `tests/test_catalog_endpoints.py` (create).

- [ ] **Step 1: `GET /api/metrics`** — return the registry catalog: a list of `{id, name, description, unit, source}` for every metric in `metrics.registry.REGISTRY`. (The metadata already exists on each `Metric`.) No params.
- [ ] **Step 2: `GET /api/schema`** — return the tables/columns the assistant may query, derived from the `rm_readonly` allowlist (schema `016_readonly_role.sql`) intersected with `information_schema.columns`, **excluding `funraise`**. Shape: `[{schema, table, columns:[{name, type}], note?}]`. Add brief per-table notes where cheap (reuse CLAUDE.md/`semantic/rm_metrics.yml` descriptions). Keep it static-cached or cheap (it's read often).
- [ ] **Step 3: Tests** — `/api/metrics` returns ≥12 metrics each with id+name+source; `/api/schema` includes `wms`/`nielsen`/`ga` tables and **does NOT include any `funraise` table** (PII guard at the catalog layer too). Real assertions.
- [ ] **Step 4: Run** `python -m pytest tests/test_catalog_endpoints.py -v` → pass; full suite green.
- [ ] **Step 5: Commit** `feat(api): metric catalog + read-only schema endpoints for the assistant`.

---

### Task 2: Finalized system prompt in-repo

**Files:** Create `dashboard/api/system-prompt.md`.

- [ ] **Step 1:** Copy Tarik's prompt (`radio-milwaukee-data-analyst-system-prompt.md`) and complete BOTH `[FILL IN]` sections verbatim from the spec's "System prompt" section (data sources & coverage incl. the "not yet loaded" list; access rules = funraise blocked, aggregates only). Keep his prose unchanged; only fill the placeholders.
- [ ] **Step 2:** Add one closing paragraph wiring the prompt to the actual tools: "You retrieve data only via `get_metric`, `list_metrics`, `query_sql`, `get_schema`. Prefer `get_metric`; call `get_schema` before `query_sql`; cite the metric id or the SQL + time window for every figure."
- [ ] **Step 3: Commit** `feat(assistant): finalized data-analyst system prompt (warehouse-grounded)`.

---

### Task 3: CopilotKit runtime (Vercel function)

**Files:** Create `dashboard/api/copilotkit.ts` (Vercel Node serverless function); `dashboard/package.json` (+`@copilotkit/runtime`, Anthropic SDK as needed); maybe `dashboard/vercel.json` (functions config).

**FIRST: pull current CopilotKit runtime docs** (adapter name, `copilotRuntimeNodeHttpEndpoint` vs Vercel handler, action/tool shape, how to inject a server-side system prompt). Confirm before coding.

- [ ] **Step 1:** Implement the function: `CopilotRuntime` + Anthropic adapter (`model = process.env.ANTHROPIC_MODEL || 'claude-sonnet-4-6'`, key from `ANTHROPIC_API_KEY`). Inject the Task-2 system prompt server-side (authoritative — not overridable by the client).
- [ ] **Step 2: Define the four server-side actions** (each `handler` does a `fetch` to `process.env.API_BASE || 'https://rm-data-loader.fly.dev'`):
  - `get_metric(id, brand?, period?, group_by?)` → `GET /api/metric/{id}?…`; return `{value, meta}`.
  - `list_metrics()` → `GET /api/metrics`.
  - `query_sql(sql)` → `POST /api/ask-sql` `{sql}`; pass through validator errors as readable messages.
  - `get_schema()` → `GET /api/schema`.
  Each action's description tells the LLM when to use it (registry-first; get_schema before query_sql).
- [ ] **Step 3:** Wire the endpoint so Vercel serves it at `/api/copilotkit` (Node handler via `copilotRuntimeNodeHttpEndpoint`, or the Vercel-specific adapter the docs show). Confirm the request/response signature for a Vercel Node function.
- [ ] **Step 4: Local check** — run the function locally (`vercel dev` or a node harness); a sample chat request returns a streamed response and a `get_metric` call hits the Fly API. Note any API corrections made vs the doc sketch.
- [ ] **Step 5: Commit** `feat(assistant): CopilotKit runtime function (Claude + metric/sql/schema tools)`.

---

### Task 4: Frontend integration (chat surface + readable context)

**Files:** `dashboard/package.json` (+`@copilotkit/react-core`, `@copilotkit/react-ui`), `dashboard/src/App.jsx` (provider + sidebar), maybe `dashboard/src/main.jsx`, `dashboard/src/app.css`.

**FIRST: confirm current CopilotKit React API** (`<CopilotKit>` props, `<CopilotSidebar>`, `useCopilotReadable`).

- [ ] **Step 1:** Wrap `App` in `<CopilotKit runtimeUrl="/api/copilotkit">`; import the CopilotKit UI CSS.
- [ ] **Step 2:** Add `<CopilotSidebar>` (collapsible) with a labels/title in RM voice ("Ask the data analyst…"). Keep it out of the way of the existing tabs.
- [ ] **Step 3: `useCopilotReadable`** — expose the live view to the agent: active tab, brand, date range, and a compact summary of the visible KPIs/payload for the current tab (so "what am I looking at / why did this move?" is grounded). Don't dump the entire payload — a focused summary.
- [ ] **Step 4: Build** `cd dashboard && npm run build` exits 0 (no unused-import/type errors). No browser yet — note chat QA is the controller's job (needs the runtime + key).
- [ ] **Step 5: Commit** `feat(dashboard): CopilotKit chat sidebar + readable dashboard context`.

---

### Task 5: Trust harness + tool tests

**Files:** `tests/test_assistant_tools.py` and/or a small TS test for the actions; a fixture Q&A doc.

- [ ] **Step 1: Tool wrapper checks** — assert each action maps to the correct Fly endpoint + shapes results (mock the fetch); `query_sql` surfaces validator errors rather than throwing opaque failures.
- [ ] **Step 2: Trust fixtures** — a documented set of probe questions + expected behavior (run manually against the deployed assistant in Task 6, recorded here):
  - a metric question → number equals `get_metric` and is cited;
  - "show me donor John Smith's gifts" → refused (PII), offers aggregate;
  - "what were underwriting contract counts in 2024?" → "not tracked yet," no fabricated number;
  - "revenue trend since 2023" → hedges (finance only ~3 months loaded).
- [ ] **Step 3: Run** backend suite green; frontend build clean.
- [ ] **Step 4: Commit** `test(assistant): tool wrappers + trust probe fixtures`.

---

### Task 6: Deploy + QA (gated)

- [ ] **Step 1: Backend** — `flyctl deploy --app rm-data-loader`; verify `/api/metrics` and `/api/schema` (no funraise) live.
- [ ] **Step 2: Secret** — set `ANTHROPIC_API_KEY` (and optional `ANTHROPIC_MODEL`) on the Vercel `dashboard` project (server-side env). **User-provided key.**
- [ ] **Step 3: Frontend + function** — deploy the Vercel project; confirm `/api/copilotkit` responds and the sidebar opens on the live dashboard.
- [ ] **Step 4: Chat QA** — run the Task-5 trust fixtures against prod: numbers match the dashboard + are cited; PII refused; unanswerable → "not tracked yet"; thin-finance hedge; no console errors. Capture results.
- [ ] **Step 5: Commit** any QA fixes. **DEPLOY/secret steps are GATED ON USER** (key + go-ahead).

---

## Notes for the controller
- Branch `tarikjmoody/moo-177-copilotkit-assistant` off `main`. Standard PR.
- The runtime + frontend tasks each START by pulling current CopilotKit docs — do not skip; the API drifts.
- Final whole-branch review on the most capable model; scrutinize: (a) the system prompt is injected server-side (not client-overridable), (b) `ANTHROPIC_API_KEY` never reaches the browser bundle, (c) `query_sql`/`get_schema` cannot reach `funraise`, (d) tool→endpoint mapping.
- Auth: dashboard + `/api/copilotkit` are public until gated — recommend Vercel protection before sharing (separate from this plan).
- After merge: update `docs/dashboard-roadmap.md` + CLAUDE.md (service status: assistant live); MOO-177 → review/done; consider Phase-2.5 (agentic UI control) as the next slice.
