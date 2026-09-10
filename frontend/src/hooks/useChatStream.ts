import { useCallback, useRef, useState } from 'react'
import { parseSSEStream } from '../lib/sseStream'
import type { ConnectionStatus, Message } from '../types/chat'

// Backend base URL. Resolves to /api per docs/architecture.md's single-entry-point
// design (nginx reverse-proxies /api to the backend, same origin as the browser) —
// defaulted here too since the value is effectively constant across environments.
const API_URL = import.meta.env.VITE_API_URL ?? '/api'

function createId() {
  return crypto.randomUUID()
}

export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([])
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const sessionId = useRef(createId())

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || connectionStatus === 'sending' || connectionStatus === 'streaming') {
        return
      }

      const userMessage: Message = { id: createId(), role: 'user', text: trimmed, status: 'complete' }
      const assistantId = createId()
      const assistantMessage: Message = { id: assistantId, role: 'assistant', text: '', status: 'streaming' }

      setMessages((prev) => [...prev, userMessage, assistantMessage])
      setConnectionStatus('sending')

      const controller = new AbortController()

      try {
        const response = await fetch(`${API_URL}/chat/stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId.current, message: trimmed }),
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`)
        }

        setConnectionStatus('streaming')

        for await (const token of parseSSEStream(response)) {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId ? { ...message, text: message.text + token } : message,
            ),
          )
        }

        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId ? { ...message, status: 'complete' } : message,
          ),
        )
        setConnectionStatus('idle')
      } catch {
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? { ...message, status: 'error', text: message.text || "Couldn't reach the backend." }
              : message,
          ),
        )
        setConnectionStatus('error')
      }
    },
    [connectionStatus],
  )

  return { messages, connectionStatus, sendMessage }
}
