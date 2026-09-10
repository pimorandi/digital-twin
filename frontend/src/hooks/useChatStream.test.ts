import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useChatStream } from './useChatStream'

function sseResponse(chunks: string[], init: ResponseInit = {}) {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder()
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(stream, init)
}

describe('useChatStream', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('accumulates streamed tokens into a single assistant message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse(['data: Hel\n\n', 'data: lo\n\n', 'data: [DONE]\n\n']),
      ),
    )

    const { result } = renderHook(() => useChatStream())

    await act(async () => {
      await result.current.sendMessage('hi')
    })

    await waitFor(() => {
      expect(result.current.connectionStatus).toBe('idle')
    })

    const assistantMessage = result.current.messages.find((m) => m.role === 'assistant')
    expect(assistantMessage?.text).toBe('Hello')
    expect(assistantMessage?.status).toBe('complete')
  })

  it('surfaces a dropped connection as an error state without throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')))

    const { result } = renderHook(() => useChatStream())

    await act(async () => {
      await result.current.sendMessage('hi')
    })

    await waitFor(() => {
      expect(result.current.connectionStatus).toBe('error')
    })

    const assistantMessage = result.current.messages.find((m) => m.role === 'assistant')
    expect(assistantMessage?.status).toBe('error')
  })
})
