/**
 * Application-layer access control.
 *
 * Clerk's production Allowlist is a paid feature, so we gate access ourselves:
 * only emails on an allowed domain (ALLOWED_EMAIL_DOMAINS, default
 * radiomilwaukee.org) or explicitly listed (ALLOWED_EMAILS, for board members'
 * personal addresses) may use the dashboard. Enforced at EVERY server entry
 * point — the copilotkit runtime, the chats proxy, and the /api/authz probe;
 * the frontend uses /api/authz only to show a friendly "not authorized" screen.
 *
 * (Vercel ignores api/ files that start with `_`, so this is a shared module,
 * not a route.)
 */
import type { IncomingMessage } from "node:http";
import { createClerkClient, verifyToken } from "@clerk/backend";

function csv(v: string | undefined): string[] {
  return (v ?? "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
}

// Allowed staff domains. Falls back to radiomilwaukee.org when unset so a missing
// env var never silently locks out staff.
function allowedDomains(): string[] {
  const d = csv(process.env.ALLOWED_EMAIL_DOMAINS);
  return d.length ? d : ["radiomilwaukee.org"];
}

export function isAllowedEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  const e = email.trim().toLowerCase();
  if (csv(process.env.ALLOWED_EMAILS).includes(e)) return true;
  const at = e.lastIndexOf("@");
  if (at < 0) return false;
  return allowedDomains().includes(e.slice(at + 1));
}

export async function emailForUser(sub: string): Promise<string | null> {
  const secretKey = process.env.CLERK_SECRET_KEY;
  if (!secretKey) return null;
  try {
    const u = await createClerkClient({ secretKey }).users.getUser(sub);
    const primary = u.emailAddresses.find((e) => e.id === u.primaryEmailAddressId);
    const addr = primary?.emailAddress ?? u.emailAddresses[0]?.emailAddress ?? null;
    return addr ? addr.toLowerCase() : null;
  } catch {
    return null;
  }
}

export async function verifiedSub(req: IncomingMessage): Promise<string | null> {
  const secretKey = process.env.CLERK_SECRET_KEY;
  if (!secretKey) return null;
  const header = req.headers["authorization"];
  const token = typeof header === "string" && header.startsWith("Bearer ") ? header.slice(7) : null;
  if (!token) return null;
  try {
    const c = (await verifyToken(token, { secretKey })) as Record<string, unknown>;
    return String(c.sub);
  } catch {
    return null;
  }
}

// Cache (sub -> allowed) briefly so we don't hit the Clerk API on every request
// (copilotkit can fire several per chat). Warm only within a function instance.
const _cache = new Map<string, { allowed: boolean; exp: number }>();
export async function isUserAllowed(sub: string): Promise<boolean> {
  const now = Date.now();
  const hit = _cache.get(sub);
  if (hit && hit.exp > now) return hit.allowed;
  const email = await emailForUser(sub);
  // Couldn't resolve the email (e.g. a transient Clerk outage) — deny THIS
  // request but don't cache it, so a legit user isn't stuck for the TTL.
  if (email === null) return false;
  const allowed = isAllowedEmail(email);
  _cache.set(sub, { allowed, exp: now + 5 * 60_000 });
  return allowed;
}
