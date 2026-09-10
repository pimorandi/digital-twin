# Architecture

Read this before changing routing, the nginx/backend boundary, session state, or
how the professional history is loaded. For the always-on essentials (and the
guardrails), see CLAUDE.md — this document is the detailed rationale behind them.

## Single entry point

The app is deployed as a **single Cloud Run service** with **nginx as the only
public entry point**. nginx does two jobs:

1. Serves the static React build (the compiled Vite output).
2. Reverse-proxies any request under `/api` to the FastAPI backend over the
   internal network.

The backend and redis are **not** internet-facing — they are reachable only from
nginx. This is the design that makes everything else simpler, so it's worth being
explicit about *why* it was chosen over running frontend and backend as two
separate public services:

- **No CORS.** The browser loads the page and makes its API calls against the same
  origin, so cross-origin rules never apply. Two separate origins would mean
  configuring and maintaining CORS headers — a common and confusing source of bugs.
- **The backend can't be hit directly.** Because only nginx is public, nobody can
  call the LLM-backed endpoints directly and run up GCP cost bypassing the UI.
- **One thing to deploy and secure.** One public URL, one TLS surface, one service
  to reason about.
- **Same behavior locally and in the cloud.** "Wherever the page came from" is
  always reachable by the browser, in local Compose and on Cloud Run alike — so
  there is no environment-specific URL wiring.

The one architectural cost — losing independent scaling of frontend and backend —
does not matter for a single-developer, low-traffic recruiter demo.

### Consequence for the frontend

The frontend calls **relative `/api/...`** paths. It must **never** call a Docker
Compose service hostname such as `http://backend:8000`: that name resolves only on
Docker's internal network, container-to-container, whereas the frontend JavaScript
runs in the **recruiter's browser**, which has no access to that network. The
frontend container only *serves* static files to the browser; it does not make the
API calls itself.

`VITE_API_URL` is therefore `/api` (or empty). Note it is baked into the JS bundle
at **build time** — changing it later requires rebuilding the frontend image.

## Request flow (one recruiter message)

1. The recruiter's browser, running the React app, sends `POST /api/chat/stream`
   with `{ session_id, message }` over HTTPS to the single service.
2. **nginx** receives it. Static-asset requests it serves directly; because the
   path is under `/api`, it reverse-proxies this one to the backend.
3. **FastAPI** builds the prompt from the conversation state and the loaded
   professional history, then calls the **LLM on GCP**.
4. Two data sources back a request, and they behave differently:
   - **redis** holds the ongoing session (per-instance, TTL-expired). A normal
     message reads/writes redis.
   - The **professional history** is loaded **once at startup** and held in memory
     (see below). A normal message does *not* re-read it.
5. As the LLM generates tokens, FastAPI **streams them back over SSE** —
   LLM → FastAPI → nginx → browser — appearing incrementally in the UI rather than
   arriving as one lump at the end.

## Professional history file

The candidate's professional-history markdown is **gitignored** and never
committed. It is **not** baked into the image — the image stays generic and
non-sensitive. The file is loaded at runtime from a **private GCS bucket**:

- On startup, the backend reads the markdown from the configured bucket via the
  GCP client libraries and holds it in memory for the agent to use.
- The bucket location comes from configuration, e.g.
  `HISTORY_GCS_URI=gs://<bucket>/<path>.md`, in the `.env` / Cloud Run environment.
- The bucket must be **private**; the Cloud Run service account needs read access
  (`roles/storage.objectViewer`).
- Updating the history is just replacing the object in the bucket — no rebuild,
  no redeploy.

**Why load once at startup:** the file is small and changes rarely, so reading it
per request would be wasted bucket calls. The trade-off is that edits to the
markdown only take effect on the next instance start; if live updates ever become
necessary, add an explicit refresh rather than reading per request.

**Local development:** the file isn't in the repo, so provide it one of two ways —
point `HISTORY_GCS_URI` at the real bucket (needs GCP credentials in the
container), or mount a local markdown file into the backend container via
`compose.prod.yaml` and have the loader fall back to a local path when
`HISTORY_GCS_URI` is unset. Keep the local file out of git.

**Scale note:** loading the whole history into the prompt (llmwiki-style) works
while the file fits comfortably in the context window. If it grows large, switch to
retrieval (chunk + embed + fetch relevant sections) rather than stuffing the whole
document in.