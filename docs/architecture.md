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
     message reads/writes redis. The stored list is trimmed to the last
     `2 * MAX_HISTORY_PAIRS` turns on every write (`LTRIM`), so it can't grow
     without bound.
   - The **professional history** is loaded **once at startup** and held in memory
     (see below). A normal message does *not* re-read it.
5. Once the reply is complete, the exchange is written to the chat-log prefix in
   the bucket (see *Chat logs*), before the stream ends.
6. As the LLM generates tokens, FastAPI **streams them back over SSE** —
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

## Chat logs

Redis is per-instance and expires, so every completed exchange (user message +
model reply) is also written to a **`chat-logs/` prefix in the same private
bucket**:

- One immutable JSON object per exchange (GCS objects can't be appended to):
  `chat-logs/<YYYY-MM-DD>/<session_id>/<utc_timestamp>_<seq>.json`, with
  `session_id`, `seq`, `timestamp`, `user`, `model`. Uploads are create-only
  (`if_generation_match=0`).
- Enabled by `CHAT_LOG_GCS_URI=gs://<bucket>/chat-logs/`; unset means no logging
  (local dev without a bucket).
- The upload is awaited inside the request (via a thread, the GCS client is sync)
  because Cloud Run throttles CPU after the response ends. A failed upload is
  logged and never breaks the chat.
- Because every exchange is durable, Redis can be trimmed freely to the LLM's
  window. Client-supplied `session_id` is validated (`[A-Za-z0-9_-]{1,64}`)
  since it becomes part of the object name.
- The client IP is deliberately **not** logged.
- IAM: besides `objectViewer`, the service account gets `roles/storage.objectCreator`
  restricted by an IAM condition to the chat-log prefix, so it can write logs but
  can't overwrite or delete anything, including the history file.
- A bucket lifecycle rule deletes objects under the prefix after
  `chat_log_retention_days` (default 90). Logs hold recruiters' free text, which is
  personal data.

## Bot protection

`/api` is public and every chat message costs a Vertex AI call, so it is gated by
a human check plus limits. All of it stays stateless (any instance can serve any
request):

1. The frontend solves a **Cloudflare Turnstile** challenge (invisible unless
   Cloudflare wants an interaction) and sends the token to `POST /api/session`.
2. The backend verifies it with Cloudflare (`TurnstileVerifier`, fails closed) and
   returns a **signed session token**: `base64url({sid, exp}) + "." + HMAC-SHA256`.
   The session id (`sid`) is generated by the server. Any instance holding
   `SESSION_SIGNING_KEY` can verify the token, so nothing is stored.
3. `POST /api/chat/stream` requires `Authorization: Bearer <token>`. The session id
   comes from the token, never from the request body. A missing, tampered or
   expired token gets a 401, and the frontend solves the challenge again and
   retries once (a new token means a new conversation).

Limits, all soft because Redis and nginx counters are per instance:
- `MAX_MESSAGES_PER_SESSION` (default 30) reuses the Redis message counter; over
  the cap returns 429. The check runs before the stream starts, so the status
  code is real.
- nginx `limit_req` per client (`/api/session` ~5 r/m, `/api/chat/` ~30 r/m), keyed
  on the last `X-Forwarded-For` entry (the address Google's front end appended).
  The key exists only in nginx memory and is never logged or stored.
- Message length is capped at 2000 characters, request bodies at 16 KB, and Gemini
  replies at `MAX_OUTPUT_TOKENS` (default 1024).
- Cloud Run `max_instances` (Terraform variable, default 2) bounds the total.
  Set a billing budget alert in the console as well.

**Secrets.** `TURNSTILE_SECRET_KEY` and `SESSION_SIGNING_KEY` are Secret Manager
secrets. Terraform only creates the empty secrets, and you add the values yourself
so they never enter the Terraform state:

    gcloud secrets versions add turnstile-secret-key --data-file=-      # paste key
    openssl rand -base64 32 | gcloud secrets versions add session-signing-key --data-file=-

Because the Cloud Run revision references `latest` of both, create the secrets and
their versions **before** the full `terraform apply`
(`terraform apply -target=google_secret_manager_secret.turnstile_secret_key
-target=google_secret_manager_secret.session_signing_key` first).
The public **site key** is baked into the frontend at build time
(`VITE_TURNSTILE_SITE_KEY`, Cloud Build substitution `_TURNSTILE_SITE_KEY`).

**Local development** uses Cloudflare's always-pass test keys (see `.env.example`).
The backend refuses to start without both secrets, so it can't run unprotected by
accident.

## Deployment

First-time / infra-only changes (Artifact Registry, IAM bindings, secret
shells) can be applied narrowly before the app exists yet:

    terraform apply -target=google_artifact_registry_repository.images \
      -target=google_project_iam_member.cloudbuild_artifact_writer

Every deploy of new frontend/backend code:

    TAG=$(date +%Y%m%d-%H%M%S)
    gcloud builds submit --config cloudbuild.yaml \
      --substitutions=_TURNSTILE_SITE_KEY=<key>,_IMAGE_TAG=$TAG
    cd terraform && terraform apply -var image_tag=$TAG

`$TAG` must be the **same value** in both commands: Cloud Build tags and
pushes `frontend:$TAG` and `backend:$TAG` (plus `:latest` for convenience),
and `terraform apply -var image_tag=$TAG` points the Cloud Run revision at
those exact tags — a constant `:latest` image string never changes, so
Terraform previously had nothing to diff on and wouldn't reliably roll out
the new image.

