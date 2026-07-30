/**
 * Manual smoke test for the CROSS-VENDOR FALLBACK model (the one that catches Anthropic 529s).
 * The chat is behind Clerk and Vercel masks the key, so this is the only way to prove the
 * OpenAI leg actually authenticates + answers before we rely on it in prod.
 *
 * Run (paste your key — it's the same one you put in Vercel):
 *   cd dashboard && OPENAI_API_KEY=sk-... node_modules/.bin/tsx api/_fallback.smoke.mts
 *
 * Override the model to try another id (e.g. if gpt-5.5 is wrong):
 *   OPENAI_API_KEY=sk-... node_modules/.bin/tsx api/_fallback.smoke.mts openai:gpt-5.1
 *
 * PASS_A = the fallback model answers a plain prompt (proves the id + key work).
 * PASS_B = with a DELIBERATELY BROKEN primary model, buildAgentStream's fallback path
 *          fires and the fallback model produces the answer (proves the wiring in _agent.ts).
 */
import { streamText } from "ai";
import { resolveModel } from "@copilotkit/runtime/v2";
import { buildAgentStream, SYNTHESIS_SYSTEM } from "./_agent.js";

const SPEC = process.argv[2] ?? process.env.FALLBACK_MODEL ?? "openai:gpt-5.5";

async function drain(stream: AsyncIterable<any>) {
  let text = "";
  let errored: string | null = null;
  for await (const part of stream) {
    if (part.type === "text-delta") text += part.text ?? part.delta ?? "";
    else if (part.type === "error") errored = String(part.error);
  }
  return { text: text.trim(), errored };
}

async function main() {
  if (!process.env.OPENAI_API_KEY) {
    console.error("Set OPENAI_API_KEY in the environment first (same key you added to Vercel).");
    process.exit(2);
  }
  console.log(`Fallback model under test: ${SPEC}\n`);

  // ── A) Direct call: does this model id + key actually answer? ──
  console.log("── A) direct call to the fallback model ──");
  const a = await drain(
    streamText({
      model: resolveModel(SPEC),
      system: "You are a terse assistant.",
      messages: [{ role: "user", content: "Reply with exactly: fallback online." }],
      maxRetries: 2,
      abortSignal: AbortSignal.timeout(60_000),
    }).fullStream,
  );
  console.log("  answer:", JSON.stringify(a.text.slice(0, 120)));
  console.log("  error:", a.errored ?? "none");
  console.log("  PASS_A:", a.text.length > 0 && !a.errored, "\n");

  // ── B) Integration: broken primary → fallback path in _agent.ts must answer ──
  console.log("── B) broken primary model → fallback fires through buildAgentStream ──");
  const input = {
    threadId: "t1", runId: "r1",
    messages: [{ id: "m1", role: "user", content: "In one sentence, say the fallback worked." }],
    tools: [], context: [], state: {},
  };
  const b = await drain(
    buildAgentStream(input, {
      model: "anthropic:claude-not-a-real-model-9999",  // guaranteed to fail → exercises fallback
      fallbackModel: SPEC,
      systemPrompt: SYNTHESIS_SYSTEM,
      serverTools: [],
      abortSignal: AbortSignal.timeout(90_000),
    }).fullStream,
  );
  console.log("  answer:", JSON.stringify(b.text.slice(0, 160)));
  console.log("  error:", b.errored ?? "none");
  // PASS = the fallback produced a real answer, NOT the graceful 'overloaded' message.
  const gracefulOnly = /briefly overloaded/i.test(b.text);
  console.log("  PASS_B (fallback answered, not the graceful error):", b.text.length > 0 && !gracefulOnly);
}

main().catch((e) => { console.error("SMOKE FAILED:", e); process.exit(1); });
