import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { isAllowedEmail } from "../api/_authz.js";

describe("isAllowedEmail", () => {
  const saved = { ...process.env };
  beforeEach(() => {
    delete process.env.ALLOWED_EMAIL_DOMAINS;
    delete process.env.ALLOWED_EMAILS;
  });
  afterEach(() => { process.env = { ...saved }; });

  it("allows the default staff domain when no env is set", () => {
    expect(isAllowedEmail("tarik@radiomilwaukee.org")).toBe(true);
  });

  it("is case-insensitive", () => {
    expect(isAllowedEmail("Tarik@RadioMilwaukee.ORG")).toBe(true);
  });

  it("rejects a non-allowed domain", () => {
    expect(isAllowedEmail("someone@gmail.com")).toBe(false);
  });

  it("allows an explicitly listed email (board personal address)", () => {
    process.env.ALLOWED_EMAILS = "boardmember@gmail.com, tarikjmoody@gmail.com";
    expect(isAllowedEmail("tarikjmoody@gmail.com")).toBe(true);
    expect(isAllowedEmail("other@gmail.com")).toBe(false);
  });

  it("honors a custom ALLOWED_EMAIL_DOMAINS list (replacing the default)", () => {
    process.env.ALLOWED_EMAIL_DOMAINS = "example.org, radiomilwaukee.org";
    expect(isAllowedEmail("a@example.org")).toBe(true);
    expect(isAllowedEmail("a@radiomilwaukee.org")).toBe(true);
    expect(isAllowedEmail("a@notallowed.com")).toBe(false);
  });

  it("rejects empty / null / malformed input", () => {
    expect(isAllowedEmail("")).toBe(false);
    expect(isAllowedEmail(null)).toBe(false);
    expect(isAllowedEmail(undefined)).toBe(false);
    expect(isAllowedEmail("no-at-sign")).toBe(false);
  });
});
