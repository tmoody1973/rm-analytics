import { describe, it, expect } from "vitest";
import { chatsUrl } from "../src/history.jsx";

describe("chatsUrl", () => {
  it("no args → /api/chats", () => expect(chatsUrl({})).toBe("/api/chats"));
  it("search → /api/chats?q=", () => expect(chatsUrl({ q: "donors" })).toBe("/api/chats?q=donors"));
  it("detail → /api/chats?id=", () => expect(chatsUrl({ id: "abc" })).toBe("/api/chats?id=abc"));
});
