# Handoff — Assistant "doesn't answer" on hard questions (2026-07-29)

Repo `~/code/rm-analytics`. Branch **`fix/assistant-always-answers`**, PR **#31** (open, unmerged, many commits). Prod: dashboard `data.radiomilwaukee.org` (Vercel), API `rm-data-loader.fly.dev` (Fly), warehouse Neon `morning-frost-30675590`.

## The problem
Users: the CopilotKit chat assistant runs its SQL tools, shows "Thought for N seconds", then **stops with no answer** — especially on hard cross-source questions (e.g. *"Remove the Jan/Feb spikes; what consistent content performs well for HYFIN's social media and website?"*). Simple questions ("how is IG engagement trending?") answer fine.

## CRITICAL constraint
**You cannot test the live chat** — it's behind Clerk sign-in. Do NOT claim a fix works from a deploy alone. Verify with these three, which you CAN use:
1. **`[agent]` instrumentation log** in Vercel: `cd dashboard && npx vercel logs https://data.radiomilwaukee.org --json | grep '\[agent\]'` → `{phase, ms, toolCalls, gatherText, synthText}`. `gatherText>0` or `synthText>0` = the answer landed.
2. **Chat archive** (Neon `chat` schema): query `chat.messages` for the latest thread; `textlen=0, tools=N` = ran tools, no answer. (Tool RESULTS aren't stored — role:"tool" rows dropped by design.)
3. **Local smoke test against the real Anthropic API** (`ANTHROPIC_API_KEY` is in `~/.radio-milwaukee/.env`), using `node_modules/.bin/tsx`. This is how every fix below was proven.

## Diagnosis journey — what was RULED OUT (don't re-investigate)
- **Not the model / not Sonnet 5 being wrong.** Raw AI SDK `streamText` with claude-sonnet-5 produces a full answer every time (proven: 1,250 chars, part types include text-start/text-delta×14/text-end). Model is fine.
- **Not the 120s Vercel timeout** (that was an EARLIER symptom, already fixed). `maxDuration:120` is in `dashboard/vercel.json`. Recent failing runs return HTTP 200 in ~61s — they complete, just with no text.
- **Not maxSteps alone.** Raising it just moves the wall. Time was never the binding limit on the recent failures.
- **Sonnet 5 emits reasoning by default**; `providerOptions.anthropic.thinking:{type:"disabled"}` does NOT turn it off (tested — reasoning parts still appear).

## Root causes found + FIXED (all deployed, in PR #31)
1. **Classic BuiltInAgent can't force an answer** → replaced with the **"aisdk" factory config** in `api/copilotkit.ts`, running our own `streamText` (`api/_agent.ts`, `buildAgentStream`). CopilotKit's factory path consumes our `fullStream` via `convertAISDKStream` (runtime `agent/converters/aisdk.mjs`).
2. **CopilotKit's converter mishandles Anthropic reasoning** (#3323 — it assumes `@ai-sdk/anthropic` never emits `reasoning-end`, but 3.0.87 does, and it drops the final text). → We **strip all `reasoning-*` parts** from the stream before CopilotKit sees them.
3. **Forcing `toolChoice:"none"` on a thinking model mid-loop yields ZERO text** (the model, shown tools it can't use, reasons and writes nothing). Reproduced locally with the real 21KB system prompt + render tools present. `activeTools:[]` fails the same way. → **TWO-PHASE**: GATHER with tools; if the model produced no text, make a **SEPARATE `streamText` call with NO tools** + everything gathered + "answer now". A no-tools call can't stall — it reliably returns prose. **Proven through the real `buildAgentStream`**: the exact failure scenario went `gatherText:0 → synthText:1872`, one clean `finish`, reasoning stripped.

### Stream-stitching rules (learned from `aisdk.mjs`, important)
- `case "finish": return;` — a `finish` part ENDS the converter. So drop the **gather** phase's `finish`; let only the final phase's `finish` through (exactly one reaches the client).
- `text-start` → new messageId (its own chat message). `text-delta` reads the **`text`** field. `text-start` reads the **`id`** field.
- Pass the system prompt via streamText's `system:` param (not unshifted into messages) — cleaner and silences the AI SDK prompt-injection warning.
- `useAgentContext` data arrives on `input.context` — append to the system prompt (as classic did) or grounding is lost.

## THE CURRENT FAILURE (root cause #4 — NOT yet fixed)
Latest run log:
```
[agent] {"phase":"gather","ms":61312,"toolCalls":9,"gatherText":0,"synthText":0}
RUN 200  RetryError [AI_RetryError]: Failed after 3 attempts. Last error: Overloaded
```
**Anthropic returned "Overloaded" (HTTP 529 — provider capacity).** The AI SDK retried 3× (default `maxRetries:2`) and threw, so the **gather phase errored before reaching synthesis** → silence. This is provider-side, made worse by our large requests (21KB prompt + many tools + thinking). Likely intermittent, and probably behind some of today's inconsistency.

## NEXT STEP (do this first in the clean context)
In `api/_agent.ts`:
1. **Bump `maxRetries`** on BOTH `streamText` calls (gather + synth) to ~**4–5** (default is 2). The SDK does exponential backoff → rides out transient 529s.
2. **Wrap `runTwoPhase` in try/catch that never leaves the user silent.** On ANY throw (Overloaded, abort, etc.), if no text has been yielded, yield hand-crafted AI SDK text parts so a message renders:
   ```ts
   const id = "err-" + Date.now();
   yield { type: "text-start", id };
   yield { type: "text-delta", id, text: "The AI service is briefly overloaded and didn't finish. Please try that again in a moment." };
   yield { type: "text-end", id };
   yield { type: "finish", finishReason: "stop" };
   ```
   (Field names verified against the converter: `text-delta`→`text`, `text-start`→`id`.) Track whether any text was yielded so you don't append the error message after a real partial answer.
3. Consider a **fallback model** on repeated overload (e.g. retry synth with `claude-sonnet-5` → a lighter model) — optional, discuss with Tarik.
4. Typecheck (`node_modules/.bin/tsc --noEmit`), `npx vitest run` (116 tests), `npm run build`, commit to `fix/assistant-always-answers`, `vercel --prod --yes`, then have Tarik run the spike question and READ THE `[agent]` LOG to confirm `synthText>0` (or a graceful error message shown).

## Also shipped in PR #31 today (verified working)
- **Chart readability** (`render-tools.jsx`, `components.jsx`): percent/currency-aware axes+tooltips (rates showed as raw `0.86`/rounded to `1`); distinct per-series colors (two lines were both blue). Proven in a browser via the pure-function render path.
- **Anti-flail prompt + schema** (`system-prompt.md`, `service/catalog_api.py`): `social_intel.fact_posts` real column names (model kept guessing `account__account_name`); "never end a turn with only tool calls" discipline. (Helped simple cases; the real fix for hard cases is the two-phase above.)

## Files touched (PR #31)
`dashboard/api/_agent.ts` (the loop — main file), `dashboard/api/_agent.smoke.mts` (manual real-API test), `dashboard/api/copilotkit.ts` (factory wiring), `dashboard/api/system-prompt.md`, `dashboard/src/render-tools.jsx`, `dashboard/src/components.jsx`, `dashboard/src/render-tools.test.jsx`, `dashboard/test/agent-loop.test.ts`, `service/catalog_api.py`.

## Versions / env
- CopilotKit **1.61.2** (runtime/react-core/core). Latest stable **1.64.1** (2.0 in preview). Upgrading MIGHT fix #3323 natively but jumps 3 minors — a deliberate separate task, not a hotfix. Our strip works regardless.
- `ai` **6.0.212**, `@ai-sdk/anthropic` **3.0.87**. `ANTHROPIC_MODEL` set in Vercel prod = `claude-sonnet-5` (code default too).
- Local smoke pattern (reproduces the failure): real `api/system-prompt.md` + a mock `query_sql` tool that returns `"partial — query another table"` (makes the model over-call) + `render_chart`/`render_table` as `input.tools` + `buildAgentStream(..., { softDeadlineMs: 9000 })`.

## Strategic note for Tarik (his question, unresolved)
He asked repeatedly whether to switch frameworks ("I don't have this issue with my app Crate"). Honest read: **the Vercel AI SDK is the layer that WORKS; CopilotKit's runtime is the fragile layer** (its reasoning handling and the toolChoice stall). You cannot "drop the AI SDK and keep CopilotKit" — CopilotKit is built on the AI SDK. If patching keeps failing, the durable path is to keep the AI SDK backend (already built in `_agent.ts`) and replace only CopilotKit's runtime/UI (e.g. AI SDK `useChat` + a lighter chat UI, or upgrade to 1.64+). Do NOT propose Claude hosted agents — worse fit. Decide with Tarik after the Overloaded fix lands.
