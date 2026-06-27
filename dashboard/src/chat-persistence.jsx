import { useEffect, useRef } from 'react'
import { useAgent } from '@copilotkit/react-core/v2'
import { useAuth } from '@clerk/react'

// Map CopilotKit messages to the save payload. Drops empty trailing assistant
// placeholders (a streamed slot that never filled). tool_calls comes from
// `toolCalls` on the message if present.
export function toSavePayload(threadId, messages) {
  const cleaned = (messages || []).filter((m) => {
    const empty = !(m.content && m.content.trim()) && !(m.toolCalls && m.toolCalls.length)
    return !(empty && m.role === 'assistant')
  })
  return {
    thread_id: threadId,
    messages: cleaned.map((m, seq) => ({
      seq,
      role: m.role === 'assistant' ? 'assistant' : 'user',
      content: m.content ?? '',
      tool_calls: m.toolCalls && m.toolCalls.length ? m.toolCalls : null,
    })),
  }
}

// Saves the whole thread once each time a run finishes (isRunning true→false).
export function ChatPersistence({ threadId }) {
  const { agent } = useAgent({ agentId: 'default' })
  const { getToken } = useAuth()
  const wasRunning = useRef(false)

  useEffect(() => {
    const running = !!agent?.isRunning
    if (wasRunning.current && !running) {
      const payload = toSavePayload(threadId, agent?.messages || [])
      if (payload.messages.length > 0) {
        getToken().then((token) =>
          fetch('/api/chats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify(payload),
          })
        ).catch(() => {})   // archive write is best-effort; never block the UI
      }
    }
    wasRunning.current = running
  }, [agent?.isRunning, agent?.messages, threadId, getToken])

  return null
}
