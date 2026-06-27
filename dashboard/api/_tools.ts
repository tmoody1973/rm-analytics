/**
 * Server-side tool definitions for the Radio Milwaukee data assistant.
 *
 * Extracted into a helper module (Vercel ignores `_`-prefixed files in api/)
 * so the tool handlers can be unit-tested independently (Task 5).
 *
 * Four tools:
 *   get_metric   – curated metric registry (prefer this first)
 *   list_metrics – catalog of curated metrics
 *   get_schema   – allowlisted table/column schema (call before query_sql)
 *   query_sql    – read-only SQL fallback (single SELECT/WITH only)
 *
 * All handlers call process.env.API_BASE (default: https://rm-data-loader.fly.dev).
 */

import { defineTool } from "@copilotkit/runtime/v2";
import { z } from "zod";

const API_BASE = () =>
  (process.env.API_BASE ?? "https://rm-data-loader.fly.dev").replace(/\/$/, "");

// ─────────────────────────────────────────────────────────────── get_metric ───

export const getMetricTool = defineTool({
  name: "get_metric",
  description: `Retrieve a single curated metric value from the Radio Milwaukee data warehouse.
PREFER THIS TOOL over query_sql whenever a curated metric exists for the question.
Returns the metric value plus metadata (name, description, unit, source).

Parameters:
  id        – metric id (e.g. "streaming_tlh", "active_donors"). Use list_metrics to discover ids.
  brand     – optional brand key: RM (88Nine) | HYFIN | RM414 (414 Music) | RLR (Rhythm Lab Radio) — omit for cross-brand aggregate
  period    – optional ISO period string, e.g. "2026-05" for monthly, "2026-W21" for weekly
  group_by  – optional grouping dimension, e.g. "month", "week", "station"`,
  parameters: z.object({
    id: z.string().describe("Metric id from the registry (use list_metrics to discover)"),
    brand: z
      .enum(["RM", "HYFIN", "RM414", "RLR"])
      .optional()
      .describe("Brand filter key. RM = 88Nine Radio Milwaukee; HYFIN = HYFIN; RM414 = 414 Music; RLR = Rhythm Lab Radio. Omit for cross-brand aggregate."),
    period: z
      .string()
      .optional()
      .describe("ISO period string, e.g. 2026-05 for monthly or 2026-W21 for weekly"),
    group_by: z
      .string()
      .optional()
      .describe("Grouping dimension, e.g. month, week, station"),
  }),
  execute: async ({ id, brand, period, group_by }) => {
    const params = new URLSearchParams();
    if (brand) params.set("brand", brand);
    if (period) params.set("period", period);
    if (group_by) params.set("group_by", group_by);

    const qs = params.toString();
    const url = `${API_BASE()}/api/metric/${encodeURIComponent(id)}${qs ? `?${qs}` : ""}`;

    const res = await fetch(url);
    const body = await res.json() as Record<string, unknown>;

    if (!res.ok) {
      const detail = (body as { detail?: string }).detail ?? `HTTP ${res.status}`;
      return { error: detail };
    }

    return body;
  },
});

// ─────────────────────────────────────────────────────────────── list_metrics ──

export const listMetricsTool = defineTool({
  name: "list_metrics",
  description: `Return the catalog of curated metrics available in the Radio Milwaukee warehouse.
Call this when you are unsure which metric id to pass to get_metric.
Each entry includes: id, name, description, unit, source.`,
  parameters: z.object({}),
  execute: async () => {
    const res = await fetch(`${API_BASE()}/api/metrics`);
    const body = await res.json() as unknown;

    if (!res.ok) {
      const detail = ((body as { detail?: string }).detail) ?? `HTTP ${res.status}`;
      return { error: detail };
    }

    return body;
  },
});

// ──────────────────────────────────────────────────────────────── get_schema ───

export const getSchemaTool = defineTool({
  name: "get_schema",
  description: `Return the allowlisted tables and columns available for SQL queries in the warehouse.
ALWAYS call this before query_sql so your SQL targets valid, accessible tables.
The funraise (donor) schema is excluded — it is blocked at the database role level.
Returns: [{schema, table, columns: [{name, type}], note?}, ...]`,
  parameters: z.object({}),
  execute: async () => {
    const res = await fetch(`${API_BASE()}/api/schema`);
    const body = await res.json() as unknown;

    if (!res.ok) {
      const detail = ((body as { detail?: string }).detail) ?? `HTTP ${res.status}`;
      return { error: detail };
    }

    return body;
  },
});

// ───────────────────────────────────────────────────────────────── query_sql ───

export const querySqlTool = defineTool({
  name: "query_sql",
  description: `Execute a read-only SQL query against the Radio Milwaukee data warehouse.
Use this ONLY for questions that no curated metric (get_metric/list_metrics) can answer.
ALWAYS call get_schema first to confirm table names and columns.

Rules enforced by the backend:
  - Single SELECT or WITH (CTE) statement only; no INSERT/UPDATE/DELETE/DDL
  - Runs as rm_readonly role — funraise schema is blocked
  - A 15-second statement timeout applies
  - The backend wraps queries in an outer LIMIT to cap result size

On success returns: {data: [...], meta: {rows, sql, via}}
On error the backend returns {detail: "..."} — this is surfaced as a readable error.`,
  parameters: z.object({
    sql: z
      .string()
      .describe("A single SELECT or WITH SQL statement. No semicolon required."),
  }),
  execute: async ({ sql }) => {
    const res = await fetch(`${API_BASE()}/api/ask-sql`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql }),
    });

    const body = await res.json() as Record<string, unknown>;

    if (!res.ok) {
      // Surface the backend's validation / permission / db error as a readable message
      const detail = (body as { detail?: string }).detail ?? `HTTP ${res.status}`;
      return { error: detail };
    }

    return body;
  },
});

// ─────────────────────────────────────────────────────────── exported array ───

export const ALL_TOOLS = [getMetricTool, listMetricsTool, getSchemaTool, querySqlTool];
