import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider, SignIn, useAuth } from '@clerk/react'
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
        /* transient; the interval retries */
      }
    }
    sync()
    const id = setInterval(sync, 50_000)
    return () => { active = false; clearInterval(id) }
  }, [getToken, copilotkit])
  return null
}

function SignInScreen() {
  return (
    <div className="signin-screen">
      <img className="signin-logo" src="/assets/logo.png" alt="Radio Milwaukee" />
      <h1>Radio Milwaukee Analytics</h1>
      <p className="signin-sub">Staff &amp; board sign-in</p>
      <SignIn routing="hash" />
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

  useEffect(() => {
    if (!isSignedIn) return
    let active = true
    getToken().then((t) => {
      if (active) setInitialHeaders(t ? { Authorization: `Bearer ${t}` } : {})
    }).catch(() => { if (active) setInitialHeaders({}) })
    return () => { active = false }
  }, [isSignedIn, getToken])

  if (!isLoaded) return <div className="loading">Loading…</div>
  if (!isSignedIn) return <SignInScreen />
  if (!initialHeaders) return <div className="loading">Signing you in…</div>
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
