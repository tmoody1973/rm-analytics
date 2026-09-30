import { describe, it, expect } from "vitest";
import { shouldFinalize, sanitizeMessages, MAX_STEPS, SOFT_DEADLINE_MS, HARD_ABORT_MS } from "../api/_agent.js";

// Guards the budget decision that forces a written answer before the run dies. The real
// end-to-end proof (against the live model) is api/_agent.smoke.mts; this pins the boundaries.
describe("shouldFinalize — force an answer before the step/time budget is spent", () => {
  const budget = { maxSteps: 15, softMs: 70_000 };

  it("keeps gathering while there's step and time budget left", () => {
    expect(shouldFinalize(0, 0, budget)).toBe(false);
    expect(shouldFinalize(5, 60_000, budget)).toBe(false);
    expect(shouldFinalize(13, 69_999, budget)).toBe(false);
  });

  it("forces a finalize on the last allowed step (never spend the ceiling on a tool call)", () => {
    expect(shouldFinalize(14, 0, budget)).toBe(true);   // step 14 = maxSteps-1
    expect(shouldFinalize(20, 0, budget)).toBe(true);
  });

  it("forces a finalize once the time budget is reached, at any step", () => {
    expect(shouldFinalize(1, 70_000, budget)).toBe(true);
    expect(shouldFinalize(1, 95_000, budget)).toBe(true);
  });

  it("the soft deadline leaves headroom before the hard abort and the 120s wall", () => {
    expect(SOFT_DEADLINE_MS).toBeLessThan(HARD_ABORT_MS);
    expect(HARD_ABORT_MS).toBeLessThan(120_000);
    // enough room after the soft deadline for the model to actually write the answer
    expect(HARD_ABORT_MS - SOFT_DEADLINE_MS).toBeGreaterThanOrEqual(20_000);
    expect(MAX_STEPS).toBeGreaterThan(1);
  });
});

// sonnet-5-5 rejects a dangling tool-call and a trailing assistant turn (both seen in prod
// logs after a frontend render tool). The sanitizer makes the replayed history valid.
describe("sanitizeMessages — valid history for a strict model (sonnet-5-5)", () => {
  const userQ = { role: "user", content: "how did HYFIN do?" };
  const asstCall = (id: string, name = "render_table") => ({
    role: "assistant",
    content: [{ type: "text", text: "" }, { type: "tool-call", toolCallId: id, toolName: name, input: {} }],
  });
  const toolResult = (id: string) => ({
    role: "tool",
    content: [{ type: "tool-result", toolCallId: id, toolName: "query_sql", output: "rows" }],
  });

  it("leaves a well-formed history untouched (server tool call WITH its result)", () => {
    const msgs = [userQ, asstCall("t1", "query_sql"), toolResult("t1"), { role: "assistant", content: "answer" }];
    // trailing assistant text is trimmed, but the call+result pair survives
    const out = sanitizeMessages(msgs);
    expect(out.slice(0, 3)).toEqual(msgs.slice(0, 3));
    expect(out[out.length - 1].role).not.toBe("assistant");
  });

  it("drops a dangling frontend tool-call whose result never came back", () => {
    const out = sanitizeMessages([userQ, asstCall("render1")]);
    const ids = out.flatMap((m: any) => Array.isArray(m.content) ? m.content : []).filter((p: any) => p?.type === "tool-call");
    expect(ids).toHaveLength(0);                // the dangling render call is gone
    expect(out[out.length - 1].role).toBe("user");
  });

  it("keeps a tool-call that DOES have a result, drops a sibling that doesn't", () => {
    const msgs = [
      userQ,
      { role: "assistant", content: [
        { type: "tool-call", toolCallId: "ok", toolName: "query_sql", input: {} },
        { type: "tool-call", toolCallId: "dangling", toolName: "render_table", input: {} },
      ] },
      toolResult("ok"),
    ];
    const out = sanitizeMessages(msgs);
    const calls = out.flatMap((m: any) => Array.isArray(m.content) ? m.content : []).filter((p: any) => p?.type === "tool-call");
    expect(calls.map((c: any) => c.toolCallId)).toEqual(["ok"]);
  });

  it("never ends on an assistant turn (the prefill 5.5 refuses)", () => {
    expect(sanitizeMessages([userQ, { role: "assistant", content: "half an answer" }]).at(-1)?.role).toBe("user");
    expect(sanitizeMessages([userQ, asstCall("x")]).at(-1)?.role).toBe("user");
  });
});
