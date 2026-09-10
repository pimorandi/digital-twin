/**
 * Minimal SSE frame parser for the chat stream response.
 *
 * Protocol assumption (backend doesn't exist yet — documenting for whoever
 * builds it): the response is `text/event-stream`, each frame is one or more
 * `data:` lines terminated by a blank line, and the stream ends with a frame
 * whose payload is the literal string `[DONE]`.
 */
export async function* parseSSEStream(response: Response): AsyncGenerator<string> {
  const body = response.body
  if (!body) return

  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''

      for (const frame of frames) {
        const payload = extractPayload(frame)
        if (payload === null) continue
        if (payload === '[DONE]') return
        yield payload
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function extractPayload(frame: string): string | null {
  const lines = frame
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trimStart())

  if (lines.length === 0) return null
  return lines.join('\n')
}
