/**
 * Vercel proxy for the chat archive. Verifies the Clerk session (any signed-in
 * user — the archive is shared), stamps identity from the token on writes, and
 * forwards to the gated Fly chat endpoints with X-Internal-Token. The browser
 * never holds the internal token and cannot set its own identity.
 */
import type { IncomingMessage, ServerResponse } from "node:http";
import { verifiedSub, emailForUser, isUserAllowed } from "./_authz.js";

const API_BASE = () =>
  (process.env.API_BASE ?? "https://rm-data-loader.fly.dev").replace(/\/$/, "");
const internalHeaders = (): Record<string, string> => ({
  "X-Internal-Token": process.env.INTERNAL_API_TOKEN ?? "",
});

export function buildFlyTarget(method: string, query: Record<string, string>): string {
  if (method === "GET" && query.id) return `/api/chats/${encodeURIComponent(query.id)}`;
  if (method === "GET" && query.q)
    return `/api/chats?q=${encodeURIComponent(query.q)}${
      query.limit ? `&limit=${encodeURIComponent(query.limit)}` : ""}`;
  return "/api/chats";
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(data));
  });
}

export default async function handler(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const sub = await verifiedSub(req);
  if (!sub) {
    res.statusCode = 401;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: "Unauthorized" }));
    return;
  }
  // App-layer allowlist: the chat archive is staff/board-only (it holds their
  // donor/financial analysis). Reject anyone not on the allowlist.
  if (!(await isUserAllowed(sub))) {
    res.statusCode = 403;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: "Forbidden" }));
    return;
  }
  const url = new URL(req.url ?? "", "http://x");
  const query = Object.fromEntries(url.searchParams.entries());
  const target = `${API_BASE()}${buildFlyTarget(req.method ?? "GET", query)}`;

  let init: RequestInit;
  if (req.method === "POST") {
    const raw = await readBody(req);
    const body = raw ? JSON.parse(raw) : {};
    body.clerk_user_id = sub;                 // stamp identity from the token
    body.user_email = await emailForUser(sub);
    init = { method: "POST",
      headers: { "Content-Type": "application/json", ...internalHeaders() },
      body: JSON.stringify(body) };
  } else {
    init = { method: "GET", headers: internalHeaders() };
  }
  const r = await fetch(target, init);
  const text = await r.text();
  res.statusCode = r.status;
  res.setHeader("Content-Type", "application/json");
  res.end(text);
}

export const config = { api: { bodyParser: false } };
