/**
 * Manual smoke test for the agent loop against the REAL Anthropic API with MOCK tools.
 * Run: cd dashboard && node_modules/.bin/tsx api/_agent.smoke.mts   (needs ANTHROPIC_API_KEY)
 *
 * Proves the guarantee mechanism, not the data:
 *   A) normal run → the model calls a tool, then writes a final answer.
 *   B) deadline already blown (softDeadlineMs=0) → the model writes an answer with NO
 *      tool calls. This is the thing the classic config could not do.
 */
import { z } from "zod";
import { defineTool } from "@copilotkit/runtime/v2";
import { buildAgentStream } from "./_agent.js";

const SYS = "You are a data assistant. Use get_data to fetch numbers, then answer in one sentence.";

const mockTools = [
  defineTool({
    name: "get_data",
    description: "Return HYFIN monthly engagement rates.",
    parameters: z.object({ metric: z.string() }),
    execute: async () => ({ rows: [{ month: "2026-05", rate: 0.55 }, { month: "2026-06", rate: 0.25 }] }),
  }),
];

const input = (q: string) => ({
  threadId: "t1", runId: "r1",
  messages: [{ id: "m1", role: "user", content: q }],
  tools: [], context: [], state: {},
});

async function drain(stream: AsyncIterable<any>) {
  let text = "";
  const toolCalls: string[] = [];
  let errored: string | null = null;
  for await (const part of stream) {
    if (part.type === "text-delta") text += part.text ?? part.delta ?? "";
    else if (part.type === "tool-call") toolCalls.push(part.toolName);
    else if (part.type === "error") errored = String(part.error);
  }
  return { text: text.trim(), toolCalls, errored };
}

async function main() {
  const model = process.env.ANTHROPIC_MODEL ?? "anthropic:claude-sonnet-5";
  const modelSpec = model.startsWith("anthropic:") ? model : `anthropic:${model}`;

  console.log("── A) normal run (should call get_data, then answer) ──");
  const a = await drain(
    buildAgentStream(input("What was HYFIN's engagement rate in May and June?"), {
      model: modelSpec, systemPrompt: SYS, serverTools: mockTools,
      abortSignal: AbortSignal.timeout(60_000),
    }).fullStream,
  );
  console.log("  tool calls:", a.toolCalls);
  console.log("  answer:", JSON.stringify(a.text.slice(0, 160)));
  console.log("  error:", a.errored ?? "none");
  console.log("  PASS_A:", a.text.length > 0 && !a.errored);

  console.log("\n── B) deadline blown from step 0 (no data yet → graceful 'couldn't retrieve') ──");
  const b = await drain(
    buildAgentStream(input("What was HYFIN's engagement rate in May and June?"), {
      model: modelSpec, systemPrompt: SYS, serverTools: mockTools,
      abortSignal: AbortSignal.timeout(60_000),
      softDeadlineMs: 0,   // every step is "out of time" → toolChoice:'none' from the start
    }).fullStream,
  );
  console.log("  tool calls (must be EMPTY):", b.toolCalls);
  console.log("  answer:", JSON.stringify(b.text.slice(0, 200)));
  const bNarratesTool = /get_data\s*\(|\{"metric"/.test(b.text);
  console.log("  PASS_B (answered in words, no tools, no narrated tool call):",
    b.text.length > 0 && b.toolCalls.length === 0 && !b.errored && !bNarratesTool);

  console.log("\n── C) THE REAL CASE: fetch on step 0, deadline forces synthesis on step 1 ──");
  // Deterministic clock: step 0's prepareStep sees elapsed 0 (fetch allowed); every later
  // call sees a blown deadline (finalize forced). Proves it synthesizes from real data.
  // call 0 = startedAt, call 1 = step-0 prepareStep (elapsed 0 → fetch), call 2+ = later steps (blown).
  let calls = 0;
  const clock = () => (calls++ < 2 ? 1_000_000 : 2_000_000);
  const c = await drain(
    buildAgentStream(input("What was HYFIN's engagement rate in May and June?"), {
      model: modelSpec, systemPrompt: SYS, serverTools: mockTools,
      abortSignal: AbortSignal.timeout(60_000),
      now: clock, softDeadlineMs: 500_000,
    }).fullStream,
  );
  console.log("  tool calls (expect exactly one get_data):", c.toolCalls);
  console.log("  answer:", JSON.stringify(c.text.slice(0, 200)));
  const cHasData = /55|0\.55|25|0\.25/.test(c.text);
  const cNarratesTool = /get_data\s*\(|\{"metric"/.test(c.text);
  console.log("  PASS_C (fetched, then a REAL answer with the numbers, no narrated tool):",
    c.toolCalls.length >= 1 && cHasData && !cNarratesTool && !c.errored);
}

main().catch((e) => { console.error("SMOKE FAILED:", e); process.exit(1); });
