/**
 * Unit tests for the four server-side tool wrappers in api/_tools.ts.
 *
 * Strategy:
 *   - Mock `@copilotkit/runtime/v2` so `defineTool` is a passthrough identity
 *     function. This lets us import _tools.ts without the full CopilotKit
 *     server runtime and test only the HTTP/shaping logic.
 *   - Stub the global `fetch` with vi.stubGlobal so no real network traffic
 *     occurs. Each test controls the simulated response.
 *   - Assert REAL behavior: correct URL + method + body/headers built by the
 *     tool, correct result shaping on success, and readable `{error}` on
 *     non-2xx — NOT just "mock returns what we told it to."
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Mock CopilotKit so we can import _tools.ts in isolation ──────────────────
// defineTool is an identity wrapper; we only care about .name and .execute.
vi.mock("@copilotkit/runtime/v2", () => ({
  defineTool: (config: {
    name: string;
    description?: string;
    parameters?: unknown;
    execute: (...args: unknown[]) => unknown;
  }) => config,
}));

// ── Import under test (after vi.mock) ────────────────────────────────────────
const { getMetricTool, listMetricsTool, getSchemaTool, querySqlTool, ALL_TOOLS } =
  await import("../api/_tools.js");

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Build a minimal fetch-compatible Response mock. */
function makeFetchResponse(
  body: unknown,
  status = 200
): Response {
  const ok = status >= 200 && status < 300;
  return {
    ok,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

// ── Setup / teardown ─────────────────────────────────────────────────────────

const originalFetch = globalThis.fetch;

beforeEach(() => {
  // Reset env overrides before each test
  delete process.env.API_BASE;
});

afterEach(() => {
  // Restore any stubbed fetch
  vi.unstubAllGlobals();
  globalThis.fetch = originalFetch;
});

// ─────────────────────────────────────────────────────────────────────────────
// 1. Name mapping
// ─────────────────────────────────────────────────────────────────────────────

describe("tool name mapping", () => {
  it("getMetricTool has name 'get_metric'", () => {
    expect(getMetricTool.name).toBe("get_metric");
  });

  it("listMetricsTool has name 'list_metrics'", () => {
    expect(listMetricsTool.name).toBe("list_metrics");
  });

  it("getSchemaTool has name 'get_schema'", () => {
    expect(getSchemaTool.name).toBe("get_schema");
  });

  it("querySqlTool has name 'query_sql'", () => {
    expect(querySqlTool.name).toBe("query_sql");
  });

  it("ALL_TOOLS contains exactly four tools with the correct names", () => {
    expect(ALL_TOOLS).toHaveLength(4);
    const names = ALL_TOOLS.map((t) => t.name);
    expect(names).toContain("get_metric");
    expect(names).toContain("list_metrics");
    expect(names).toContain("get_schema");
    expect(names).toContain("query_sql");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. getMetricTool — endpoint mapping + query string building
// ─────────────────────────────────────────────────────────────────────────────

describe("getMetricTool", () => {
  it("calls GET /api/metric/{id} with no query string when no optional params given", async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse({ id: "streaming_tlh", value: 4200 })
    );
    vi.stubGlobal("fetch", mockFetch);

    const result = await getMetricTool.execute({ id: "streaming_tlh" });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("https://rm-data-loader.fly.dev/api/metric/streaming_tlh");
    expect(url).not.toContain("?");
    expect(init).toBeUndefined();          // GET — no body/headers passed
    expect(result).toEqual({ id: "streaming_tlh", value: 4200 });
  });

  it("builds the full query string when brand, period, and group_by are all provided", async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse({ id: "streaming_tlh", value: 3800 })
    );
    vi.stubGlobal("fetch", mockFetch);

    await getMetricTool.execute({
      id: "streaming_tlh",
      brand: "RM",
      period: "2026-05",
      group_by: "month",
    });

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit | undefined];
    const parsed = new URL(url);
    expect(parsed.pathname).toBe("/api/metric/streaming_tlh");
    expect(parsed.searchParams.get("brand")).toBe("RM");
    expect(parsed.searchParams.get("period")).toBe("2026-05");
    expect(parsed.searchParams.get("group_by")).toBe("month");
  });

  it("URL-encodes the metric id in the path", async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse({ id: "active donors", value: 42 })
    );
    vi.stubGlobal("fetch", mockFetch);

    await getMetricTool.execute({ id: "active donors" });

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toContain("/api/metric/active%20donors");
  });

  it("returns the parsed JSON body unchanged on a 200 response", async () => {
    const payload = { id: "active_donors", value: 1024, unit: "donors", source: "funraise" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(makeFetchResponse(payload)));

    const result = await getMetricTool.execute({ id: "active_donors" });

    expect(result).toEqual(payload);
  });

  it("returns {error: detail} when the response is non-2xx and detail is present", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        makeFetchResponse({ detail: "metric id 'bogus' not found in registry" }, 404)
      )
    );

    const result = await getMetricTool.execute({ id: "bogus" });

    expect(result).toEqual({ error: "metric id 'bogus' not found in registry" });
  });

  it("falls back to 'HTTP <status>' when non-2xx body has no detail field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(makeFetchResponse({}, 503))
    );

    const result = await getMetricTool.execute({ id: "streaming_tlh" });

    expect(result).toEqual({ error: "HTTP 503" });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. listMetricsTool — endpoint + shaping
// ─────────────────────────────────────────────────────────────────────────────

describe("listMetricsTool", () => {
  it("calls GET /api/metrics with no body", async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse([{ id: "streaming_tlh", name: "TLH" }])
    );
    vi.stubGlobal("fetch", mockFetch);

    await listMetricsTool.execute({});

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("https://rm-data-loader.fly.dev/api/metrics");
    expect(init).toBeUndefined();
  });

  it("returns the parsed JSON body unchanged on 200", async () => {
    const catalog = [
      { id: "streaming_tlh", unit: "hours" },
      { id: "active_donors", unit: "donors" },
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(makeFetchResponse(catalog)));

    const result = await listMetricsTool.execute({});

    expect(result).toEqual(catalog);
  });

  it("returns {error: detail} on non-2xx with detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ detail: "service unavailable" }, 503))
    );

    const result = await listMetricsTool.execute({});

    expect(result).toEqual({ error: "service unavailable" });
  });

  it("falls back to 'HTTP <status>' when no detail field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ message: "gone" }, 410))
    );

    const result = await listMetricsTool.execute({});

    expect(result).toEqual({ error: "HTTP 410" });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. getSchemaTool — endpoint + shaping
// ─────────────────────────────────────────────────────────────────────────────

describe("getSchemaTool", () => {
  it("calls GET /api/schema with no body", async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse([{ schema: "wms", table: "fact_hourly_listening", columns: [] }])
    );
    vi.stubGlobal("fetch", mockFetch);

    await getSchemaTool.execute({});

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("https://rm-data-loader.fly.dev/api/schema");
    expect(init).toBeUndefined();
  });

  it("returns the parsed JSON body unchanged on 200", async () => {
    const schema = [{ schema: "wms", table: "fact_daily_cume", columns: [{ name: "cume", type: "integer" }] }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(makeFetchResponse(schema)));

    const result = await getSchemaTool.execute({});

    expect(result).toEqual(schema);
  });

  it("returns {error: detail} on non-2xx with detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ detail: "schema endpoint disabled" }, 403))
    );

    const result = await getSchemaTool.execute({});

    expect(result).toEqual({ error: "schema endpoint disabled" });
  });

  it("falls back to 'HTTP <status>' when no detail field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(makeFetchResponse({}, 500))
    );

    const result = await getSchemaTool.execute({});

    expect(result).toEqual({ error: "HTTP 500" });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. querySqlTool — endpoint + method + headers + body + error surfacing
// ─────────────────────────────────────────────────────────────────────────────

describe("querySqlTool", () => {
  const testSql = "SELECT station_code, SUM(tlh) AS total_tlh FROM wms.fact_hourly_listening GROUP BY station_code";

  it("calls POST /api/ask-sql with Content-Type: application/json and the SQL in the body", async () => {
    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse({ data: [{ station_code: "RM88", total_tlh: 4200 }], meta: { rows: 1 } })
    );
    vi.stubGlobal("fetch", mockFetch);

    await querySqlTool.execute({ sql: testSql });

    expect(mockFetch).toHaveBeenCalledOnce();
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://rm-data-loader.fly.dev/api/ask-sql");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    // Verify the SQL is serialized into the body correctly
    expect(JSON.parse(init.body as string)).toEqual({ sql: testSql });
  });

  it("returns the parsed JSON body unchanged on 200", async () => {
    const payload = { data: [{ station_code: "RM88", total_tlh: 4200 }], meta: { rows: 1, via: "rm_readonly" } };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(makeFetchResponse(payload)));

    const result = await querySqlTool.execute({ sql: testSql });

    expect(result).toEqual(payload);
  });

  it("surfaces validator errors as readable {error} — NOT a thrown exception", async () => {
    // This is the critical safety test: the backend rejects INSERT/UPDATE/DDL
    // with a 400 + detail. The tool must convert it to {error} without throwing.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        makeFetchResponse(
          { detail: "only a single SELECT or WITH statement is allowed" },
          400
        )
      )
    );

    // Must resolve — not reject — even on 400
    await expect(
      querySqlTool.execute({ sql: "DELETE FROM wms.fact_hourly_listening" })
    ).resolves.toEqual({ error: "only a single SELECT or WITH statement is allowed" });
  });

  it("surfaces funraise schema block as readable {error} — NOT a thrown exception", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        makeFetchResponse(
          { detail: "permission denied for schema funraise" },
          403
        )
      )
    );

    await expect(
      querySqlTool.execute({ sql: "SELECT * FROM funraise.fact_transactions" })
    ).resolves.toEqual({ error: "permission denied for schema funraise" });
  });

  it("falls back to 'HTTP <status>' when non-2xx body has no detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(makeFetchResponse({ message: "timeout" }, 504))
    );

    const result = await querySqlTool.execute({ sql: testSql });

    expect(result).toEqual({ error: "HTTP 504" });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. API_BASE env override
// ─────────────────────────────────────────────────────────────────────────────

describe("API_BASE override via process.env.API_BASE", () => {
  it("uses the env var prefix instead of the default fly.dev URL", async () => {
    // Set the override BEFORE importing the factory call inside execute.
    // The factory reads process.env.API_BASE lazily (per-call), so setting
    // it here affects the next execute() call.
    process.env.API_BASE = "https://staging.example.com";

    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse({ id: "streaming_tlh", value: 100 })
    );
    vi.stubGlobal("fetch", mockFetch);

    await getMetricTool.execute({ id: "streaming_tlh" });

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit | undefined];
    expect(url.startsWith("https://staging.example.com/")).toBe(true);
    expect(url).not.toContain("fly.dev");
  });

  it("strips a trailing slash from API_BASE before building the URL", async () => {
    process.env.API_BASE = "https://staging.example.com/";

    const mockFetch = vi.fn().mockResolvedValueOnce(
      makeFetchResponse([])
    );
    vi.stubGlobal("fetch", mockFetch);

    await listMetricsTool.execute({});

    const [url] = mockFetch.mock.calls[0] as [string, RequestInit | undefined];
    // Should not produce double slash
    expect(url).toBe("https://staging.example.com/api/metrics");
  });
});
