import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearSessionToken, getSessionToken } from '../lib/session'
import { useChatStream } from './useChatStream'

vi.mock('../lib/session', () => ({
  getSessionToken: vi.fn().mockResolvedValue('token-1'),
  clearSessionToken: vi.fn(),
}))

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
    vi.mocked(getSessionToken).mockResolvedValue('token-1')
    vi.mocked(clearSessionToken).mockClear()
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

  it('sends the session token as a Bearer header', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(['data: [DONE]\n\n']))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatStream())
    await act(async () => {
      await result.current.sendMessage('hi')
    })

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer token-1')
    expect(JSON.parse(init.body as string)).toEqual({ message: 'hi' })
  })

  it('gets a fresh token and retries once when the token is rejected with 401', async () => {
    vi.mocked(getSessionToken).mockResolvedValueOnce('stale').mockResolvedValueOnce('fresh')
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(sseResponse(['data: ok\n\n', 'data: [DONE]\n\n']))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatStream())
    await act(async () => {
      await result.current.sendMessage('hi')
    })

    expect(clearSessionToken).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const retryInit = fetchMock.mock.calls[1][1] as RequestInit
    expect((retryInit.headers as Record<string, string>).Authorization).toBe('Bearer fresh')
    expect(result.current.messages.find((m) => m.role === 'assistant')?.text).toBe('ok')
  })

  it('does not retry a second 401 and reports an error', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useChatStream())
    await act(async () => {
      await result.current.sendMessage('hi')
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.current.connectionStatus).toBe('error')
  })

  it('shows a limit message when the backend answers 429', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 429 })))

    const { result } = renderHook(() => useChatStream())
    await act(async () => {
      await result.current.sendMessage('hi')
    })

    expect(result.current.connectionStatus).toBe('error')
    expect(result.current.errorMessage).toMatch(/limit/i)
    expect(result.current.messages.find((m) => m.role === 'assistant')?.text).toMatch(/limit/i)
  })
})
