import { describe, it, expect } from "vitest";
import { toSavePayload } from "../src/chat-persistence.jsx";

describe("toSavePayload", () => {
  it("maps messages to {seq, role, content, tool_calls} and keeps order", () => {
    const msgs = [
      { role: "user", content: "How many donors?" },
      { role: "assistant", content: "14,087.", toolCalls: [{ name: "query_sql", args: { sql: "SELECT ..." } }] },
    ];
    const p = toSavePayload("t-1", msgs);
    expect(p.thread_id).toBe("t-1");
    expect(p.messages.map((m) => m.seq)).toEqual([0, 1]);
    expect(p.messages[0].role).toBe("user");
    expect(p.messages[1].tool_calls).toEqual([{ name: "query_sql", args: { sql: "SELECT ..." } }]);
  });

  it("drops empty trailing assistant placeholders (no content, no tool calls)", () => {
    const msgs = [
      { role: "user", content: "hi" },
      { role: "assistant", content: "" },
    ];
    const p = toSavePayload("t-2", msgs);
    expect(p.messages).toHaveLength(1);
  });

  it("drops tool/system messages and never coerces other roles to user", () => {
    const msgs = [
      { role: "user", content: "Who are top donors?" },
      { role: "tool", content: '{"data":[{"name":"Alice","amount":500}]}' },
      { role: "assistant", content: "The top donor is Alice with $500." },
    ];
    const p = toSavePayload("t-3", msgs);
    // tool message must be dropped
    expect(p.messages.find((m: { role: string }) => m.role === "tool")).toBeUndefined();
    // assistant message must stay as 'assistant', not relabeled to 'user'
    const asst = p.messages.find((m: { role: string }) => m.role === "assistant");
    expect(asst).toBeDefined();
    expect(asst!.role).toBe("assistant");
    // only 2 messages: user + assistant
    expect(p.messages).toHaveLength(2);
  });
});
