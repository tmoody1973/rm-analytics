import { describe, it, expect } from "vitest";
import { buildFlyTarget } from "../api/chats.js";

describe("buildFlyTarget", () => {
  it("GET with no params → /api/chats", () => {
    expect(buildFlyTarget("GET", {})).toBe("/api/chats");
  });
  it("GET with q → /api/chats?q=...", () => {
    expect(buildFlyTarget("GET", { q: "donors" })).toBe("/api/chats?q=donors");
  });
  it("GET with id → /api/chats/{id} (id wins over q)", () => {
    expect(buildFlyTarget("GET", { id: "abc", q: "x" })).toBe("/api/chats/abc");
  });
  it("POST → /api/chats", () => {
    expect(buildFlyTarget("POST", {})).toBe("/api/chats");
  });
});
