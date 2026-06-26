import React from 'react'
import { createRoot } from 'react-dom/client'
import { CopilotKit } from '@copilotkit/react-core'
import '@copilotkit/react-ui/styles.css'
import './theme.css'
import './app.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <CopilotKit runtimeUrl="/api/copilotkit">
      <App />
    </CopilotKit>
  </React.StrictMode>
)
