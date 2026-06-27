import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider, SignIn, useAuth, useClerk } from '@clerk/react'
import { CopilotKit, useCopilotKit } from '@copilotkit/react-core/v2'
import '@copilotkit/react-core/v2/styles.css'
import './theme.css'
import './app.css'
import App from './App.jsx'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!PUBLISHABLE_KEY) {
  // Fail loud: without the key the app can't enforce auth, and we won't render
  // an ungated dashboard.
  throw new Error('Missing VITE_CLERK_PUBLISHABLE_KEY — auth is required to run the dashboard.')
}

// Pushes the Clerk session token into CopilotKit so every chat request to
// /api/copilotkit carries `Authorization: Bearer <token>` (the function verifies
// it server-side). Refreshed ahead of the ~60s Clerk token expiry.
function TokenSync() {
  const { getToken } = useAuth()
  const { copilotkit } = useCopilotKit()
  useEffect(() => {
    let active = true
    const sync = async () => {
      try {
        const token = await getToken()
        if (active && copilotkit) {
          copilotkit.setHeaders({ Authorization: token ? `Bearer ${token}` : null })
        }
      } catch {
        /* transient; the next trigger retries */
      }
    }
    sync()
    // Active tab: refresh well ahead of the ~60s Clerk token TTL.
    const id = setInterval(sync, 30_000)
    // Backgrounded tabs THROTTLE/suspend setInterval, so an idle tab's token can
    // lapse and the next request would send an expired token (→ 401). Refresh the
    // instant the tab is revealed/refocused — before the user can submit — so a
    // returning idle tab never carries a stale token.
    const onVisible = () => { if (document.visibilityState === 'visible') sync() }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', sync)
    return () => {
      active = false
      clearInterval(id)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', sync)
    }
  }, [getToken, copilotkit])
  return null
}

function SignInScreen() {
  return (
    <div className="signin-screen">
      <img className="signin-logo" src="/assets/logo-cream.png" alt="Radio Milwaukee" />
      <h1>Radio Milwaukee Analytics</h1>
      <p className="signin-sub">Staff &amp; board sign-in</p>
      <SignIn routing="hash" />
    </div>
  )
}

// Signed in, but the email isn't on the app-layer allowlist (staff domain or an
// explicitly allowed address). The data endpoints reject this user server-side
// too; this screen is just the friendly explanation + a way out.
function AccessDenied() {
  const { signOut } = useClerk()
  return (
    <div className="signin-screen">
      <img className="signin-logo" src="/assets/logo-cream.png" alt="Radio Milwaukee" />
      <h1>Access restricted</h1>
      <p className="signin-sub">
        This dashboard is for Radio Milwaukee staff and board. Your account isn’t on the
        list yet — if you think it should be, contact Tarik.
      </p>
      <button className="signin-out" onClick={() => signOut()}>Sign out</button>
    </div>
  )
}

// Hook-based gate (clerk-react-patterns): never render the dashboard until a
// signed-in session is confirmed. We also fetch the first token BEFORE mounting
// CopilotKit so its initial /info request already carries auth (no 401 race);
// TokenSync then keeps it refreshed.
function Gate() {
  const { isLoaded, isSignedIn, getToken } = useAuth()
  const [initialHeaders, setInitialHeaders] = useState(null)
  const [authz, setAuthz] = useState('checking')   // 'checking' | 'allowed' | 'denied'

  useEffect(() => {
    if (!isSignedIn) return
    let active = true
    getToken().then(async (t) => {
      if (!active) return
      setInitialHeaders(t ? { Authorization: `Bearer ${t}` } : {})
      try {
        const r = await fetch('/api/authz', { headers: t ? { Authorization: `Bearer ${t}` } : {} })
        const body = await r.json().catch(() => ({}))
        if (active) setAuthz(body.authorized ? 'allowed' : 'denied')
      } catch {
        if (active) setAuthz('denied')
      }
    }).catch(() => { if (active) { setInitialHeaders({}); setAuthz('denied') } })
    return () => { active = false }
  }, [isSignedIn, getToken])

  if (!isLoaded) return <div className="loading">Loading…</div>
  if (!isSignedIn) return <SignInScreen />
  if (authz === 'denied') return <AccessDenied />
  if (!initialHeaders || authz === 'checking') return <div className="loading">Signing you in…</div>
  return (
    <CopilotKit runtimeUrl="/api/copilotkit" useSingleEndpoint={false} headers={initialHeaders}>
      <TokenSync />
      <App />
    </CopilotKit>
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/">
      <Gate />
    </ClerkProvider>
  </React.StrictMode>
)
