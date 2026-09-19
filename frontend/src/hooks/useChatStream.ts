import { useCallback, useState } from 'react'
import { clearSessionToken, getSessionToken } from '../lib/session'
import { parseSSEStream } from '../lib/sseStream'
import type { ConnectionStatus, Message } from '../types/chat'

// Backend base URL. Resolves to /api per docs/architecture.md's single-entry-point
// design (nginx reverse-proxies /api to the backend, same origin as the browser) —
// defaulted here too since the value is effectively constant across environments.
const API_URL = import.meta.env.VITE_API_URL ?? '/api'

const LIMIT_MESSAGE = 'Message limit reached. Please try again later.'

function createId() {
  return crypto.randomUUID()
}

class LimitReachedError extends Error {}

// The backend derives the session from the Bearer token, so an expired/invalid
// token (401) is fixed by solving the challenge again — retried once.
async function postChat(text: string, signal: AbortSignal): Promise<Response> {
  for (let attempt = 0; ; attempt++) {
    const token = await getSessionToken()
    const response = await fetch(`${API_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ message: text }),
      signal,
    })
    if (response.status === 401 && attempt === 0) {
      clearSessionToken()
      continue
    }
    return response
  }
}

export function useChatStream() {
  const [messages, setMessages] = useState<Message[]>([])
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

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
      setErrorMessage(null)

      const controller = new AbortController()

      try {
        const response = await postChat(trimmed, controller.signal)

        if (response.status === 429) {
          throw new LimitReachedError()
        }
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
      } catch (error) {
        console.error(error)
        const limitReached = error instanceof LimitReachedError
        if (limitReached) setErrorMessage(LIMIT_MESSAGE)
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? { ...message, status: 'error', text: message.text || (limitReached ? LIMIT_MESSAGE : "Couldn't reach the backend.") }
              : message,
          ),
        )
        setConnectionStatus('error')
      }
    },
    [connectionStatus],
  )

  return { messages, connectionStatus, errorMessage, sendMessage }
}
