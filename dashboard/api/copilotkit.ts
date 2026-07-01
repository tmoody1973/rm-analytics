/**
 * CopilotKit runtime — Vercel Node serverless function
 * Served at: /api/copilotkit
 *
 * Uses CopilotKit v2 API:
 *   - @copilotkit/runtime/v2  → CopilotRuntime, BuiltInAgent, createCopilotRuntimeHandler
 *   - @copilotkit/runtime/v2/node → createCopilotNodeHandler
 *
 * Key design decisions:
 *   - System prompt loaded from disk (api/system-prompt.md) at module init; authoritative server-side.
 *   - forwardSystemMessages: false (v2 default) — client cannot override instructions.
 *   - ANTHROPIC_API_KEY read from process.env; never exposed to the browser.
 *   - Model: process.env.ANTHROPIC_MODEL || "anthropic:claude-sonnet-5" (v2 provider:model format).
 *   - Four server-side tools extracted to api/_tools.ts for independent testability (Task 5).
 */

import type { IncomingMessage, ServerResponse } from "node:http";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

import { CopilotRuntime, BuiltInAgent, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { createCopilotNodeHandler } from "@copilotkit/runtime/v2/node";

import { ALL_TOOLS } from "./_tools.js";
import { verifiedSub, isUserAllowed } from "./_authz.js";

// ──────────────────────────────────────────── system prompt (server-authoritative) ───

/**
 * Resolve __dirname in an ESM/CJS-agnostic way so this works under both
 * Vercel's esbuild bundler (CJS output) and native ESM runtimes.
 */
const _dirname =
  typeof __dirname !== "undefined"
    ? __dirname
    : path.dirname(fileURLToPath(import.meta.url));

/**
 * Load the system prompt from the markdown file that lives alongside this function.
 * Vercel bundles the api/ directory and the system-prompt.md file is co-located,
 * so this path is valid both locally and in production.
 *
 * Loading at module init (not per-request) keeps latency low; the content is static.
 */
function loadSystemPrompt(): string {
  const promptPath = path.resolve(_dirname, "system-prompt.md");
  try {
    return fs.readFileSync(promptPath, "utf-8");
  } catch (err) {
    // Fail loud at startup — a missing system prompt is a hard misconfiguration.
    throw new Error(
      `[copilotkit] Cannot load system prompt from ${promptPath}: ${String(err)}`
    );
  }
}

const systemPrompt = loadSystemPrompt();

// ──────────────────────────────────────────────────────────────── model config ───

/**
 * CopilotKit v2 expects the model in "provider:model-id" format.
 * ANTHROPIC_MODEL may be set as either:
 *   - bare:        claude-sonnet-5   (we prepend "anthropic:")
 *   - prefixed:    anthropic:claude-sonnet-5   (used as-is)
 */
function resolveModel(): string {
  const raw = process.env.ANTHROPIC_MODEL ?? "claude-sonnet-5";
  return raw.startsWith("anthropic:") ? raw : `anthropic:${raw}`;
}

// ────────────────────────────────────────────────── runtime + handler build ───

const agent = new BuiltInAgent({
  model: resolveModel(),
  // prompt is the server-side system prompt field in v1.61.x BuiltInAgentClassicConfig.
  // forwardSystemMessages defaults to false — client cannot inject or override instructions.
  prompt: systemPrompt,
  tools: ALL_TOOLS,
  // Room for real multi-step analysis: get_schema → write SQL → recover from a
  // query error → requery → synthesize. 5 was too low and cut complex answers off.
  maxSteps: 15,
});

const runtime = new CopilotRuntime({
  agents: { default: agent },
});

// createCopilotRuntimeHandler returns a fetch-native (Request → Response) handler.
// createCopilotNodeHandler wraps it to a Node (IncomingMessage, ServerResponse) handler
// that Vercel's Node runtime expects.
const fetchHandler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
  cors: true,
});

const nodeHandler = createCopilotNodeHandler(fetchHandler);

// ──────────────────────────────────────────────────────────── Vercel export ───

// ──────────────────────────────────────────────────────────── auth gate ───

/**
 * Verify the caller holds a valid Clerk session AND is on the app-layer
 * allowlist (staff domain or an explicitly allowed email — see _authz.ts).
 * FAIL CLOSED: missing secret / token / membership → rejected. This is the real
 * protection — gating only the UI would leave this endpoint (and the warehouse
 * tools behind it) reachable by a direct API call.
 */
async function isAuthorized(req: IncomingMessage): Promise<boolean> {
  const sub = await verifiedSub(req);
  if (!sub) return false;
  return isUserAllowed(sub);
}

/**
 * Default export — Vercel Node serverless function handler.
 * Signature: (req: IncomingMessage, res: ServerResponse) => void | Promise<void>
 */
export default async function handler(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const pathOnly = (req.url ?? "").split("?")[0];

  // CORS preflight carries no Authorization header — let the runtime answer it.
  if (req.method === "OPTIONS") return nodeHandler(req, res);

  // `/info` is a non-sensitive capability probe (runtime version + agent/tool
  // names, no data). The CopilotKit client fetches it on init without auth, so
  // allow it through. The data-bearing endpoints (agent run, where tools hit the
  // warehouse) stay gated below.
  if (req.method === "GET" && pathOnly.endsWith("/info")) return nodeHandler(req, res);

  if (!(await isAuthorized(req))) {
    res.statusCode = 401;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: "Unauthorized — Radio Milwaukee staff/board access only." }));
    return;
  }
  return nodeHandler(req, res);
}

// Vercel config: disable body parsing (CopilotKit streams the body itself)
export const config = {
  api: {
    bodyParser: false,
  },
};
