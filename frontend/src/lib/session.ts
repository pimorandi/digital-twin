/**
 * Human-verified chat session.
 *
 * Solves an (invisible unless needed) Cloudflare Turnstile challenge, exchanges
 * it at POST /api/session for a signed session token, and caches that token
 * until shortly before it expires. See docs/architecture.md, "Bot protection".
 */
const API_URL = import.meta.env.VITE_API_URL ?? '/api'
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY
const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
const EXPIRY_MARGIN_SECONDS = 30

interface TurnstileApi {
  render: (container: HTMLElement, options: Record<string, unknown>) => string
  remove: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

let cached: { token: string; expiresAt: number } | null = null
let pending: Promise<string> | null = null
let scriptPromise: Promise<TurnstileApi> | null = null

export function clearSessionToken() {
  cached = null
}

export function getSessionToken(): Promise<string> {
  if (cached && Date.now() < cached.expiresAt) return Promise.resolve(cached.token)
  pending ??= acquireSessionToken().finally(() => {
    pending = null
  })
  return pending
}

async function acquireSessionToken(): Promise<string> {
  const turnstileToken = await solveChallenge()
  const response = await fetch(`${API_URL}/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ turnstile_token: turnstileToken }),
  })
  if (!response.ok) {
    throw new Error(`Session request failed with status ${response.status}`)
  }
  const { session_token, expires_in } = (await response.json()) as {
    session_token: string
    expires_in: number
  }
  cached = {
    token: session_token,
    expiresAt: Date.now() + Math.max(expires_in - EXPIRY_MARGIN_SECONDS, 0) * 1000,
  }
  return session_token
}

function loadTurnstile(): Promise<TurnstileApi> {
  scriptPromise ??= new Promise<TurnstileApi>((resolve, reject) => {
    if (window.turnstile) return resolve(window.turnstile)
    const script = document.createElement('script')
    script.src = SCRIPT_URL
    script.async = true
    script.onload = () =>
      window.turnstile ? resolve(window.turnstile) : reject(new Error('Turnstile unavailable'))
    script.onerror = () => reject(new Error('Failed to load Turnstile'))
    document.head.appendChild(script)
  }).catch((error) => {
    scriptPromise = null // allow a retry on the next attempt
    throw error
  })
  return scriptPromise
}

async function solveChallenge(): Promise<string> {
  const turnstile = await loadTurnstile()
  // Fixed-position so an interactive challenge, if Cloudflare decides one is
  // needed, is actually visible; otherwise the widget stays empty.
  const container = document.createElement('div')
  container.style.cssText = 'position:fixed;bottom:16px;right:16px;z-index:50'
  document.body.appendChild(container)

  return new Promise<string>((resolve, reject) => {
    const cleanup = () => {
      turnstile.remove(widgetId)
      container.remove()
    }
    const widgetId = turnstile.render(container, {
      sitekey: SITE_KEY,
      appearance: 'interaction-only',
      // We remove the widget on failure, so Turnstile's own auto-retry would find nothing to reset.
      retry: 'never',
      callback: (token: string) => {
        cleanup()
        resolve(token)
      },
      'error-callback': (errorCode: string) => {
        cleanup()
        reject(new Error(`Turnstile challenge failed (error ${errorCode})`))
      },
    })
  })
}
