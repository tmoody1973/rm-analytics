/**
 * Authorization probe for the frontend gate. Verifies the Clerk session and
 * reports whether this user is allowed to use the dashboard (app-layer allowlist
 * — see _authz.ts). The data endpoints enforce the same check independently, so
 * this is purely so the UI can show a clean "not authorized" screen.
 */
import type { IncomingMessage, ServerResponse } from "node:http";
import { verifiedSub, emailForUser, isAllowedEmail } from "./_authz.js";

export default async function handler(req: IncomingMessage, res: ServerResponse): Promise<void> {
  res.setHeader("Content-Type", "application/json");
  const sub = await verifiedSub(req);
  if (!sub) {
    res.statusCode = 401;
    res.end(JSON.stringify({ authorized: false }));
    return;
  }
  const email = await emailForUser(sub);
  const authorized = isAllowedEmail(email);
  res.statusCode = 200;
  res.end(JSON.stringify({ authorized, email: authorized ? email : null }));
}

export const config = { api: { bodyParser: false } };
