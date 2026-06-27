import { describe, it, expect } from "vitest";
import { chatsUrl, toolCallSummary, timeBucket, groupThreads } from "../src/history.jsx";

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

// Use whole-day offsets from `now` so the buckets are timezone-robust
// (timeBucket compares calendar days in local time, like the browser does).
const NOW = new Date("2026-06-27T17:00:00Z").getTime();
const DAY = 86400000;
const ago = (days: number) => new Date(NOW - days * DAY).toISOString();

describe("timeBucket", () => {
  it("now → Today", () => expect(timeBucket(ago(0), NOW)).toBe("Today"));
  it("one day ago → Yesterday", () => expect(timeBucket(ago(1), NOW)).toBe("Yesterday"));
  it("four days ago → This Week", () => expect(timeBucket(ago(4), NOW)).toBe("This Week"));
  it("sixty days ago → Earlier", () => expect(timeBucket(ago(60), NOW)).toBe("Earlier"));
  it("invalid date → Earlier", () => expect(timeBucket("not-a-date", NOW)).toBe("Earlier"));
});

describe("groupThreads", () => {
  it("orders buckets Today → Earlier and keeps only non-empty ones", () => {
    const groups = groupThreads([
      { thread_id: "a", updated_at: ago(0) },
      { thread_id: "b", updated_at: ago(60) },
      { thread_id: "c", updated_at: ago(0) },
    ], NOW);
    expect(groups.map((g) => g.label)).toEqual(["Today", "Earlier"]);
    expect(groups[0].items.map((t) => t.thread_id)).toEqual(["a", "c"]);
    expect(groups[1].items.map((t) => t.thread_id)).toEqual(["b"]);
  });
});
