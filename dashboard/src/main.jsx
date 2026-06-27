import React from 'react'
import { createRoot } from 'react-dom/client'
import { CopilotKit } from '@copilotkit/react-core/v2'
import '@copilotkit/react-core/v2/styles.css'
import './theme.css'
import './app.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* v2 provider + useSingleEndpoint={false} to match our multi-route v2 runtime
        (the v1-compat bridge defaults to single-endpoint, which 404s against /agent/default/run). */}
    <CopilotKit runtimeUrl="/api/copilotkit" useSingleEndpoint={false}>
      <App />
    </CopilotKit>
  </React.StrictMode>
)
