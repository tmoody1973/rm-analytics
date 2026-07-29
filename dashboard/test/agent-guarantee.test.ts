import { describe, it, expect, vi, beforeEach } from "vitest";

/**
 * Proves the core guarantee: buildAgentStream's fullStream ALWAYS ends with user-visible
 * text and exactly one `finish`, even when the model throws (Overloaded). The live proof is
 * api/_agent.smoke.mts; this pins the failure paths without a network call by mocking the
 * model layer. `streamText` is scripted per call: gather = 1st, synth = 2nd, fallback = 3rd.
 */

type Part = { type: string; text?: string; id?: string; finishReason?: string };

// A scripted streamText result: yields the given parts, then resolves response.messages.
function scriptedResult(parts: Part[]) {
  return {
    async *[Symbol.asyncIterator]() {},
    fullStream: (async function* () { for (const p of parts) yield p; })(),
    response: Promise.resolve({ messages: [] }),
  };
}
function throwingResult() {
  // Only fullStream throws (the real 529 failure mode). response stays resolved so the mock
  // never leaves a dangling rejected promise when the catch path skips awaiting it.
  return {
    fullStream: (async function* () { throw new Error("Overloaded"); })(),
    response: Promise.resolve({ messages: [] }),
  };
}

const queue: Array<ReturnType<typeof scriptedResult> | ReturnType<typeof throwingResult>> = [];
vi.mock("ai", async (orig) => ({
  ...(await orig<typeof import("ai")>()),
  streamText: vi.fn(() => queue.shift() ?? scriptedResult([{ type: "finish", finishReason: "stop" }])),
}));
vi.mock("@copilotkit/runtime/v2", () => ({
  resolveModel: (s: string) => s,
  convertMessagesToVercelAISDKMessages: () => [],
  convertToolDefinitionsToVercelAITools: () => ({}),
  convertToolsToVercelAITools: () => ({}),
}));

const { buildAgentStream, OVERLOADED_MESSAGE } = await import("../api/_agent.js");

async function collect(model = "anthropic:x", fallbackModel?: string): Promise<Part[]> {
  const { fullStream } = buildAgentStream(
    { messages: [], tools: [] },
    { model, fallbackModel, systemPrompt: "sys", serverTools: [], abortSignal: new AbortController().signal },
  );
  const out: Part[] = [];
  for await (const p of fullStream as AsyncIterable<Part>) out.push(p);
  return out;
}

const textOf = (parts: Part[]) => parts.filter(p => p.type === "text-delta").map(p => p.text).join("");
const finishCount = (parts: Part[]) => parts.filter(p => p.type === "finish").length;

describe("buildAgentStream — always ends with text + exactly one finish", () => {
  beforeEach(() => { queue.length = 0; });

  it("gather answers on its own → its finish passes through (exactly one)", async () => {
    queue.push(scriptedResult([
      { type: "text-start", id: "a" },
      { type: "text-delta", id: "a", text: "Here is the answer." },
      { type: "text-end", id: "a" },
      { type: "finish", finishReason: "stop" },
    ]));
    const parts = await collect();
    expect(textOf(parts)).toBe("Here is the answer.");
    expect(finishCount(parts)).toBe(1);
  });

  it("gather is silent → synthesis produces the answer (exactly one finish)", async () => {
    queue.push(scriptedResult([{ type: "tool-call" }, { type: "finish", finishReason: "stop" }])); // gather: tools, no text
    queue.push(scriptedResult([
      { type: "text-start", id: "s" },
      { type: "text-delta", id: "s", text: "Synthesized answer." },
      { type: "finish", finishReason: "stop" },
    ]));
    const parts = await collect();
    expect(textOf(parts)).toBe("Synthesized answer.");
    expect(finishCount(parts)).toBe(1);
  });

  it("primary synth throws → fallback model answers", async () => {
    queue.push(scriptedResult([{ type: "tool-call" }, { type: "finish", finishReason: "stop" }])); // gather silent
    queue.push(throwingResult());                                                                   // primary synth 529
    queue.push(scriptedResult([{ type: "text-delta", id: "f", text: "Fallback answer." }, { type: "finish", finishReason: "stop" }]));
    const parts = await collect("anthropic:x", "openai:gpt-5.1");
    expect(textOf(parts)).toBe("Fallback answer.");
    expect(finishCount(parts)).toBe(1);
  });

  it("everything throws → graceful error message + exactly one finish (never silent)", async () => {
    queue.push(throwingResult()); // gather
    queue.push(throwingResult()); // synth
    const parts = await collect();
    expect(textOf(parts)).toBe(OVERLOADED_MESSAGE);
    expect(finishCount(parts)).toBe(1);
  });
});
