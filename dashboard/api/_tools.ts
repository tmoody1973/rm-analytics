/**
 * Server-side tool definitions for the Radio Milwaukee data assistant.
 *
 * Extracted into a helper module (Vercel ignores `_`-prefixed files in api/)
 * so the tool handlers can be unit-tested independently (Task 5).
 *
 * Five tools:
 *   get_metric             – curated metric registry (prefer this first)
 *   list_metrics           – catalog of curated metrics
 *   get_schema             – allowlisted table/column schema (call before query_sql)
 *   query_sql              – read-only SQL fallback (single SELECT/WITH only)
 *   get_newsletter_content – full body + topic tags for one Mailchimp newsletter
 *
 * All handlers call process.env.API_BASE (default: https://rm-data-loader.fly.dev).
 *
 * These Fly endpoints are gated behind a shared secret (INTERNAL_API_TOKEN) — this
 * Vercel function is the only authorized caller. Every fetch sends it as the
 * X-Internal-Token header. The browser never calls the Fly endpoints directly.
 */

import { defineTool } from "@copilotkit/runtime/v2";
import { z } from "zod";

const API_BASE = () =>
  (process.env.API_BASE ?? "https://rm-data-loader.fly.dev").replace(/\/$/, "");

// Shared secret sent to the gated Fly tool endpoints. Empty string if unset so
// the header is always present and deterministic (the server rejects a bad token).
const internalHeaders = (): Record<string, string> => ({
  "X-Internal-Token": process.env.INTERNAL_API_TOKEN ?? "",
});

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

    const res = await fetch(url, { headers: internalHeaders() });
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
    const res = await fetch(`${API_BASE()}/api/metrics`, { headers: internalHeaders() });
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
Includes the funraise (donor) schema — DE-IDENTIFIED only (no names/emails/phones); see its table notes.
Returns: [{schema, table, columns: [{name, type}], note?}, ...]`,
  parameters: z.object({}),
  execute: async () => {
    const res = await fetch(`${API_BASE()}/api/schema`, { headers: internalHeaders() });
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
  - Runs as rm_readonly role — includes DE-IDENTIFIED funraise (donor) data; never surface individual PII
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
      headers: { "Content-Type": "application/json", ...internalHeaders() },
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

// ─────────────────────────────────────────────────── get_newsletter_content ───

export const getNewsletterContentTool = defineTool({
  name: "get_newsletter_content",
  description: `Retrieve the full body text and topic tags of a single Radio Milwaukee email newsletter (Mailchimp campaign).
Use this when the user wants to read, summarize, or understand what a SPECIFIC newsletter actually said —
e.g. "summarize the latest HYFIN newsletter" or "what stories did the June newsletter feature?".

For aggregate/correlation questions ACROSS many newsletters ("what topics drive opens?"), use query_sql instead:
the tags live in email_esp.fact_campaign_enrichment and the open/click rates in email_esp.stg_campaigns_report
(join on campaign_id = stg_campaigns_report.id).

Parameters:
  campaign_id – the Mailchimp campaign id (= email_esp.stg_campaigns_report.id). Use query_sql to find ids
                by subject/date if you don't have one.

Returns: {campaign_id, subject_line, send_time, word_count, content_type, primary_theme, topics[],
          featured_artists[], plain_text (capped at 8000 chars), truncated}.
On a missing/unknown id the backend returns 404 — surfaced as a readable {error}.`,
  parameters: z.object({
    campaign_id: z
      .string()
      .describe("Mailchimp campaign id (= email_esp.stg_campaigns_report.id)"),
  }),
  execute: async ({ campaign_id }) => {
    const url = `${API_BASE()}/api/newsletter-content/${encodeURIComponent(campaign_id)}`;
    const res = await fetch(url, { headers: internalHeaders() });
    const body = await res.json() as Record<string, unknown>;

    if (!res.ok) {
      const detail = (body as { detail?: string }).detail ?? `HTTP ${res.status}`;
      return { error: detail };
    }

    return body;
  },
});

// ─────────────────────────────────────────────────────────── exported array ───

export const ALL_TOOLS = [
  getMetricTool,
  listMetricsTool,
  getSchemaTool,
  querySqlTool,
  getNewsletterContentTool,
];
