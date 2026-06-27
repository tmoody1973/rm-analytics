import { describe, it, expect } from "vitest";
import { chatsUrl, toolCallSummary } from "../src/history.jsx";

describe("chatsUrl", () => {
  it("no args → /api/chats", () => expect(chatsUrl({})).toBe("/api/chats"));
  it("search → /api/chats?q=", () => expect(chatsUrl({ q: "donors" })).toBe("/api/chats?q=donors"));
  it("detail → /api/chats?id=", () => expect(chatsUrl({ id: "abc" })).toBe("/api/chats?id=abc"));
});

describe("toolCallSummary", () => {
  it("parses AG-UI function shape with JSON string arguments", () => {
    const result = toolCallSummary([
      { function: { name: "query_sql", arguments: '{"sql":"SELECT 1"}' } },
    ]);
    expect(result).toEqual([{ name: "query_sql", args: { sql: "SELECT 1" } }]);
  });

  it("handles simple {name, args} shape", () => {
    const result = toolCallSummary([{ name: "get_metric", args: { metric: "cume" } }]);
    expect(result).toEqual([{ name: "get_metric", args: { metric: "cume" } }]);
  });

  it("returns empty array for null/undefined input", () => {
    expect(toolCallSummary(null)).toEqual([]);
    expect(toolCallSummary(undefined)).toEqual([]);
  });
});
