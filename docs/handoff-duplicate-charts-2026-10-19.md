# Handoff — duplicate charts/tables in the assistant (2026-10-19)

> Open this first in the clean session. Two separate problems share one root; one is fixed, one is NOT.

## TL;DR
- **FIXED + live:** streaming questions hung + burned ~$100 — `query_sql` fed up to 1000 raw
  rows into the loop (265K input tokens/run). Capped the assistant at **60 rows** + aggregate
  steering. PR **#33** (branch `fix/sql-row-cap-cost`, auto-merge armed), deployed to prod.
- **NOT fixed (reverted):** the assistant draws the **same chart/table 3×** on multi-viz
  questions. Several fixes tried and reverted. Current prod should be rolled back to the
  simple render (see "State" below) — duplicates are visible but at least charts SHOW.

## The duplicate — confirmed root cause
Prod is on **claude-sonnet-5** (confirmed via a new `[agent] event:start` log line). The
duplicate is NOT model-specific — it happens on sonnet-5 too (our earlier "5 is clean"
assumption was never tested on a multi-viz question).

**Mechanism (confirmed in logs + CopilotKit docs):** one question = **~5 agent runs**
(`POST /api/copilotkit/agent/default/run`). CopilotKit re-invokes the agent after each
frontend-tool call; each run re-emits the SAME `render_chart`/`render_table` call with a
**new toolCallId, same args** → the same chart drawn multiple times. CopilotKit's own
diagnostic: *"two different tool-call ids, same args = the agent requested it twice."*

This is BOTH the visible duplicate AND a **5× cost** problem (5 runs per question).

## What was tried and why each failed
1. **`followUp: false`** on the render tools (the documented fix for side-effect tools) —
   **shadowed.** We also put a server-side `execute` on the same tool names; CopilotKit says
   *"when a frontend and server tool share a name, the server silently wins the merge,"* so the
   frontend `followUp` flag is ignored. There is **no server-side `followUp`** (grepped the
   runtime types — none). Commit `0ff4a88` (kept; harmless but inert).
2. **Client-side dedup** (keep the first toolCallId for a given content, skip later dupes) —
   **broke rendering.** CopilotKit displays a LATER render (end-of-run snapshot) than the first;
   keeping-first suppressed the one it actually shows → **no chart at all**, and the model text
   said *"using the table above"* referencing the suppressed render. Reverted (`ee5578b`).
   `render` DOES receive `toolCallId` + `status` (in `RenderToolProps`) — a future dedup must
   key on the DISPLAYED/complete render, not the first.
3. (Earlier, during the 5.5 eval): `disableParallelToolUse`, a conversation `sanitizer`, and
   the server `execute` — none stopped the re-render on 5.5. See [[assistant-caching-and-sonnet-5-5]].

## Observed behavior is INCONSISTENT (key clue)
Same question, different renders across asks:
- Once: table drawn **3×**.
- Once: **no chart or table at all**, just text (the keep-first dedup suppressed the displayed render; model text said *"using the table above"*).
- Once (dedup deploy): **chart 2×, table 1× in one answer** — pattern was chart → table → chart(again, "from the top") → text.
This run-to-run inconsistency = the streaming-render vs end-of-run-snapshot lifecycle; the
"kept" render is sometimes the visible one, sometimes not. **Do not design a dedup blind —
instrument the client first (step 2 below) to see which render CopilotKit actually displays.**

## Next steps (ranked) for the clean session
1. **Upgrade CopilotKit** — installed **1.61.2**, latest **1.79.1** (18 minors behind). The
   frontend-tool render lifecycle + followUp handling have almost certainly improved; a known
   tool-forwarding regression (1.62.x) is long fixed. Highest leverage, but test for breaking
   changes (we're on the v2 API: `@copilotkit/react-core/v2`, `runtime/v2`).
2. **Instrument the client first** — log every render call's `{toolCallId, status, name, title}`
   to the browser console for one question; have Tarik paste it. That shows the EXACT lifecycle
   (how many ids, which is displayed) so a correct dedup/fix can be designed with data, not guesses.
3. **Stop the extra runs at the source** — the real fix for both dup AND cost. Likely means not
   double-defining render tools (frontend `useFrontendTool` + server `execute` in `_agent.ts`),
   or reworking the custom two-phase loop vs CopilotKit's native frontend-tool round-trip.
4. **Then** moving to sonnet-5-5 is safe (Tarik wants it for speed/cost) — the dup is model-agnostic.

## State of the code
- Branch `fix/duplicate-charts-followup` (off `fix/sql-row-cap-cost`): has the cost fix +
  `followUp:false` (inert) + the `[agent] event:start` model log + the **reverted** dedup.
  138/138 tests green.
- **Prod is currently on `dashboard-jplq077ld` (the broken dedup — NO charts).** Deploy the
  revert to restore charts: `cd ~/code/rm-analytics/dashboard && vercel --prod` from this branch.
- Cost fix PR #33 is separate and auto-merge-armed.
- Key files: `dashboard/src/render-tools.jsx` (render tools + render callbacks),
  `dashboard/api/_agent.ts` (custom two-phase loop + server execute for render tools, line ~168),
  `dashboard/api/_tools.ts` (query_sql 60-row cap).
- Useful log probe: `vercel logs --deployment <url>` (CLI 64 syntax), grep `event.*start` (model)
  and count `agent/default/run` (runs per question). Neon MCP is NOT connected to this org —
  can't query the prod `chat` archive via MCP.
