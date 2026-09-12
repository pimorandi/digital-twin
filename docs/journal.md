# Project Journal

Chronological log of applied changes to the digital-twin project. Entries are
appended at the bottom (newest last). Read this file at the start of a new
session to understand what was last done and where the project stands,
without needing to reconstruct it from full git history.

Entries are written by the `journal-logger` subagent, triggered by asking to
"log the changes" / "update the journal", or via `/journal`.

---

## 2026-09-11 — Set up the project journal

**Summary**: Added this journal plus a `journal-logger` subagent and a
`/journal` slash command so future sessions can log applied changes and a
new session can pick up context (what changed, why, and current dev stage)
without re-deriving it from git history.

**Files changed**:
- `docs/journal.md` — new, this file
- `.claude/agents/journal-logger.md` — new subagent definition
- `.claude/commands/journal.md` — new `/journal` slash command

**Current stage**: Repo has an initial architecture and frontend
implementation (see `docs/architecture.md`, `CLAUDE.md`). This entry only
adds project tooling for tracking future changes; no application code
changed.

**Next steps**: Use `/journal` or ask to "log the changes" after making
meaningful changes to backend, frontend, or infra, to keep this file current.

---

## 2026-09-11 — First backend skeleton, end-to-end SSE path

**Summary**: `backend/` and `tests/` existed but were empty. Built the first
FastAPI backend skeleton so the full browser → nginx → backend SSE path works
end-to-end, returning a fixed canned response — redis, GCS history loading,
and the real LLM call are all deliberately deferred to later sessions. Root
`pyproject.toml` was extended with runtime + dev deps and pytest/ruff config,
and a deliberate call was made (confirmed with the user) to keep backend
tests under the existing root-level `tests/` directory rather than nesting
under `backend/tests/`, using `pythonpath = ["backend"]` so `from app.main
import app` resolves from there. Verified locally via uvicorn + curl, and via
the full `docker compose -f compose.prod.yaml up --build` stack, curling
through nginx's published port to confirm the real proxy path (nginx →
`backend:8000`) streams multiple SSE frames ending in `[DONE]`. The
`python-test-writer` subagent then added 6 unit tests covering the happy path
and validation errors; smoke tests were out of scope since
`compose.test.yaml` doesn't exist yet and there's no external resource to
exercise for real in this skeleton. Also discussed, without changing code,
how `backend/app/api` and `backend/app/schemas` map onto the clean-
architecture layers described in `CLAUDE.md`'s "Backend code organization"
section: both are "presentation," and the current flat layout deliberately
skips nesting under a `presentation/` package until the other layers
(entities/infrastructure/application/persistence) exist and nesting pays off.

**Files changed**:
- `backend/app/main.py` — new; FastAPI app, includes the chat router under
  prefix `/api`, no CORS middleware (nginx makes frontend/backend same-origin)
- `backend/app/api/chat.py` — new; `POST /chat/stream` returns a
  `StreamingResponse` (`text/event-stream`) streaming a fixed placeholder
  string word-by-word as `data: <word>\n\n` frames, ending with
  `data: [DONE]\n\n`
- `backend/app/schemas/chat.py` — new; `ChatRequest` DTO (`session_id`,
  `message`)
- `docker/Dockerfile-backend`, `docker/Dockerfile-backend.dockerignore` — new;
  plain pip install of fastapi/uvicorn, mirrors `docker/Dockerfile-ui`
- `compose.prod.yaml` — added a `backend` service with no published port
  (internal-only, per the guardrail against exposing backend to the
  internet); added `depends_on: [backend]` to the frontend service
- `pyproject.toml` — added fastapi/uvicorn runtime deps and a dev group
  (pytest, httpx, ruff); added `[tool.pytest.ini_options]`
  (`pythonpath = ["backend"]`, `testpaths = ["tests"]`) and `[tool.ruff]`
- `uv.lock` — new, generated as a side effect of `uv sync`
- `tests/api/test_chat.py` — new; 6 unit tests (200 + `text/event-stream`
  content type; full SSE frame sequence matches the fixed response
  word-by-word and ends with `[DONE]`; 422 on missing `message`, missing
  `session_id`, empty body, and wrong type for `message`)

**Current stage**: Backend skeleton is up and reachable end-to-end with a
canned response; unit-tested (6 passed) and `ruff check backend tests`
clean; no real chat logic (LLM/redis/GCS) wired in yet.

**Next steps**: Wire up redis session storage (persistence layer), GCS
history loading + LLM call (infrastructure layer), and the actual chat use
case (application layer); then revisit whether to restructure `backend/app`
into explicit entities/infrastructure/persistence/application/presentation
packages per `CLAUDE.md`. `compose.test.yaml` and smoke-test infra still
don't exist.

---

## 2026-09-11 — Redis-backed session storage

**Summary**: Made `POST /api/chat/stream` track, per `session_id`, how many
messages that session has sent, backed by Redis, streaming the count back as
the "answer" in place of the old fixed placeholder string — the first bit of
real (non-canned) backend behavior. This also revisited and overturned the
previous entry's call to leave `api/`/`schemas/` flat: `backend/app` is now
properly restructured into the entities/infrastructure/persistence/
application/presentation layering described in `CLAUDE.md`, with `api/` and
`schemas/` moved (via `git mv`, preserving history) under a new
`presentation/` package. Deliberate architecture call: `application` depends
directly on the concrete `persistence.RedisSessionStore` class rather than
through a Protocol/interface — CLAUDE.md's dependency rules only restrict
inbound imports to `entities` and `infrastructure`, they don't mandate
ports-and-adapters between `application` and `persistence` for a single
Redis implementation, so no speculative abstraction was added. Verified
end-to-end for real against the full `docker compose -f compose.prod.yaml up
--build` stack (frontend + backend + redis), curling through nginx: the same
`session_id` incremented 1 → 2 across two requests, and a different
`session_id` started fresh at 1, with no backend errors; stack was then torn
down. The `python-test-writer` subagent then fixed the tests broken by the
`presentation/` move and added new persistence tests; final result 11 tests
passed, `ruff check backend tests` clean.

**Files changed**:
- `backend/app/entities/config.py` — new; frozen `Settings` dataclass +
  `load_settings()` reading `REDIS_URL` (default `redis://redis:6379/0`) and
  `SESSION_TTL_SECONDS` (default `3600`) from env — config helpers live in
  `entities` per `CLAUDE.md`
- `backend/app/persistence/session_store.py` — new; `RedisSessionStore`
  wraps `redis.asyncio.Redis`; `increment_message_count(session_id)` `INCR`s
  key `session:<id>:message_count` and refreshes its TTL each call (sliding
  TTL — an active session never expires mid-conversation, only after a full
  TTL of inactivity)
- `backend/app/application/chat_use_case.py` — new; `ChatUseCase
  .handle_message(session_id, message)` delegates to the session store;
  `message` currently unused, kept for when real LLM logic lands
- `backend/app/api/` → `backend/app/presentation/api/`,
  `backend/app/schemas/` → `backend/app/presentation/schemas/` — moved via
  `git mv`
- `backend/app/presentation/api/chat.py` — now streams a single
  `data: <count>\n\n` frame + `data: [DONE]\n\n` (dropped the old word-by-
  word streaming of a fixed string); added `get_chat_use_case(request) ->
  ChatUseCase` reading `request.app.state.chat_use_case`, injected via
  FastAPI `Depends`
- `backend/app/main.py` — added an `asynccontextmanager` `lifespan` that
  builds a lazy `redis.asyncio.Redis` client from `load_settings()`, wraps it
  in `RedisSessionStore`, stores a `ChatUseCase` on `app.state.chat_use_case`
  at startup, and closes the client at shutdown; deliberately no eager Redis
  ping/health-check or retry logic — Redis-down resilience is out of scope
  and deferred, a first request just surfaces a 500 if Redis is unreachable
- `compose.prod.yaml` — added a `redis` service (`redis:7-alpine`, no
  published port, per the guardrail against exposing redis to the internet);
  `backend` now has `depends_on: [redis]` and `REDIS_URL`/
  `SESSION_TTL_SECONDS` env vars with `${VAR:-default}` fallbacks
- `docker/Dockerfile-backend`, `pyproject.toml` — added `redis>=5.0,<6` to
  backend deps
- `pyproject.toml` — added `[tool.ruff.lint.flake8-bugbear]
  extend-immutable-calls = ["fastapi.Depends"]` to fix a `B008` false
  positive on `Depends(get_chat_use_case)` as a function-argument default,
  rather than suppressing with inline `# noqa`
- `.env`, `.env.example` — added `REDIS_URL=redis://redis:6379/0` and
  `SESSION_TTL_SECONDS=3600`
- `tests/api/test_chat.py` — updated import paths for the `presentation/`
  move; replaced fixed-string assertions with assertions on the new
  single-count SSE frame; added an autouse fixture clearing
  `app.dependency_overrides` after each test; overrides `get_chat_use_case`
  with an `AsyncMock(spec=ChatUseCase)` so unit tests never touch real Redis
- `tests/persistence/test_session_store.py` — new; mocks
  `redis.asyncio.Redis` via `AsyncMock` to verify `RedisSessionStore` calls
  `incr`/`expire` with the right key/TTL; since `pytest-asyncio` isn't a
  declared dev dependency, these async tests are driven via
  `asyncio.run(...)` inside plain sync test functions rather than pulling in
  a new dependency out of scope for this task

**Current stage**: Backend now has real per-session state via Redis, fully
wired through Docker Compose and verified through the real
nginx → backend → redis path; unit-tested (11 passed), `ruff check backend
tests` clean. Still no LLM call, no GCS history loading (`infrastructure`
layer still empty/unused), and no smoke tests / `compose.test.yaml` (still
doesn't exist).

**Next steps**: GCS history loading + real LLM call (infrastructure layer),
wiring the actual chat use case to use the LLM/history instead of just the
message count, `compose.test.yaml` / smoke-test infra still needs to be
created, and Redis-down resilience/error handling was explicitly deferred.

---

## 2026-09-12 — Terraform for GCP infrastructure (backend identity + bucket)

**Summary**: Before Cloud Run can be defined (deferred to a later request),
gave the backend a GCP identity: a service account that can read the
professional-history object from the existing GCS bucket and call Gemini via
Vertex AI, and brought that pre-existing bucket under Terraform management so
the environment is reproducible from code rather than hand-configured. No
IaC existed anywhere in the repo before this; the new files went into an
empty `terraform/` directory already present at the repo root. Two design
questions were confirmed with the user before implementing: Terraform itself
authenticates via Application Default Credentials (no key needed for
Terraform's own auth), and — overriding the initially-recommended "no key"
default — Terraform does generate and write a JSON key for the new backend
service account now, for local Docker Compose dev (Cloud Run will later
attach the SA natively and won't need a key). Mid-planning, the user also
corrected the initial scope: the bucket was originally going to be treated
as pre-existing/unmanaged, but the user asked for it to be created/managed
by Terraform as well, so a `google_storage_bucket` resource was added to
bring the already-existing bucket under Terraform's management. Every IAM
grant deliberately uses the additive `_iam_member` resource type, never the
authoritative `_iam_binding`/`_policy` variants, since those would replace
the *entire* set of principals holding a role on a pre-existing bucket/
project and could silently revoke access other principals already have.
Verified via `terraform fmt`, `terraform init` (google ~>6.50.0, local
~>2.9.1), and `terraform validate` ("The configuration is valid"); confirmed
via a `git add -n terraform/` dry-run that `.gitignore` rules track exactly
the intended files. `terraform plan`/`apply` were explicitly not run against
real GCP — the real project ID isn't known yet and creating live billed
resources (service account, IAM grants, a long-lived key) needs explicit
confirmation first.

**Files changed**:
- `terraform/versions.tf` — new; `required_providers` (`hashicorp/google`
  ~>6.0, `hashicorp/local` ~>2.0, the latter for writing the generated key to
  disk), `required_version >=1.5`
- `terraform/variables.tf` — new; `project_id`/`bucket_name` required with no
  defaults (filled in via the user's own tfvars); `region` defaults to
  `us-central1`; `bucket_location` defaults to `US` (GCS bucket locations are
  a different axis from Vertex AI regions); `service_account_id`/
  `display_name` defaults; optional `credentials_file` (empty by default);
  `backend_key_output_path` defaults to `./backend-sa-key.json`
- `terraform/main.tf` — new; `google_storage_bucket.history` (name/location
  from vars, `uniform_bucket_level_access = true`,
  `public_access_prevention = "enforced"` — enforces the CLAUDE.md guardrail
  against making the bucket public directly in code, `force_destroy = false`
  so a stray `terraform destroy` can't wipe the candidate's history data);
  `google_project_service.aiplatform` enabling `aiplatform.googleapis.com`;
  `google_service_account.backend` (new SA); `google_storage_bucket_iam_member`
  granting exactly `roles/storage.objectViewer` on the bucket (the precise
  role `docs/architecture.md` already specified, nothing broader);
  `google_project_iam_member` granting `roles/aiplatform.user` at the project
  level; `google_service_account_key.backend_key` +
  a `local_file` resource writing the decoded key to
  `backend_key_output_path` (0600 permissions)
- `terraform/outputs.tf` — new; `service_account_email` (for later Cloud Run
  use) and `backend_key_path`
- `terraform/terraform.tfvars.example` — new; committed parameter-file
  template with placeholders, mirroring the repo's existing `.env`/
  `.env.example` pattern
- `terraform/.terraform.lock.hcl` — new, generated by `terraform init`;
  deliberately not gitignored, so provider versions stay reproducible
- `.gitignore` — added a Terraform section: `terraform/.terraform/`,
  `terraform/*.tfstate*`, `terraform/*.tfvars` (with a
  `!terraform/terraform.tfvars.example` negation to keep the template
  tracked), `terraform/*.json` (catches the generated SA key),
  `terraform/crash.log`

**Current stage**: Backend now has real per-session state via Redis (prior
entry) plus a Terraform-defined GCP service account with GCS read and
Vertex AI access, ready to be attached to a Cloud Run service once that's
defined. Terraform config is validated but not yet applied against real
infrastructure — the bucket already exists in GCP but not in Terraform's
state, so a one-time `terraform import google_storage_bucket.history
<bucket_name>` is required before the first `plan`/`apply` in this
environment.

**Next steps**: Run `terraform import` on the bucket, then `plan`/`apply`
against the real GCP project once the project ID is confirmed (explicit
user confirmation before applying, since this creates live billed
resources); define the Cloud Run service in Terraform, attaching this
service account (no key needed there); wire the backend's actual GCS
history loading and Vertex AI/Gemini call (infrastructure layer, still
unimplemented in the Python code — only the Terraform-side access exists so
far); `compose.test.yaml` / smoke-test infra still doesn't exist; Redis-down
resilience/error handling remains deferred.

---

## 2026-09-12 — GCS-backed professional history loader

**Summary**: Picked up where the prior Terraform entry's "next steps" left
off: implemented the Python-side code to actually read the professional-
history markdown from the GCS bucket at startup and hold it in memory, per
`docs/architecture.md`'s design (load once at startup, GCS primary with a
local-file fallback for dev, never make the bucket public). The GCP-side
access (service account, IAM) already existed from the prior session's
Terraform work — this closes the loop on the Python side. This is the first
code in the `infrastructure` layer, per `CLAUDE.md`'s clean-architecture
doc. Explicitly out of scope (confirmed with the user before implementing):
`ChatUseCase` was not changed to consume the loaded history — there's still
no LLM call anywhere in the codebase, so there's nothing yet to hand this
content to; that's a deliberate scope boundary, not an oversight. Verified
directly against the real bucket outside Docker (using the SA key generated
in the prior Terraform session) — confirmed successful download of the real
professional-history content (not echoed further, per the guardrail against
surfacing candidate data unnecessarily) — and again end-to-end through the
full `docker compose -f compose.prod.yaml up --build` stack (frontend +
backend + redis, now with `terraform/` mounted in), with backend logs
showing clean startup and no GCS errors; also sanity-checked the existing
`/api/chat/stream` endpoint still works through nginx. Stack was torn down
afterward. The `python-test-writer` subagent then added unit tests using
obviously-fake bucket names/content per the guardrail against real bucket
names/content in tests. Final result: 19 tests passed total (11 pre-existing
+ 8 new), `ruff check backend tests` clean.

**Files changed**:
- `backend/app/infrastructure/__init__.py` — new; first file in this layer
- `backend/app/infrastructure/history_loader.py` — new; `GcsHistoryLoader`,
  constructor-injected `storage.Client | None` (same style as the existing
  `RedisSessionStore` — client built by the caller, not internally), plus
  `gcs_uri: str | None` and `local_fallback_path: str | None`; `load() ->
  str` prefers the GCS branch (parses `gcs_uri` via a module-level
  `_parse_gcs_uri` helper using `urllib.parse.urlparse` — bucket = netloc,
  object path = path with leading slash stripped, raises `ValueError` on a
  non-`gs://` scheme — then calls
  `client.bucket(...).blob(...).download_as_text()`), falls back to reading
  `local_fallback_path` via `pathlib.Path.read_text` if `gcs_uri` isn't set,
  and raises `ValueError` if neither is configured; `client` is only ever
  touched on the GCS branch, so a pure local-fallback setup needs zero GCP
  credentials, not even to construct the loader
- `backend/app/entities/config.py` — `Settings` gained `history_gcs_uri:
  str | None` and `history_local_path: str | None`, read from the existing
  `HISTORY_GCS_URI` and the new, optional `HISTORY_LOCAL_PATH` env vars
- `backend/app/main.py` — in `lifespan`, after the existing Redis/
  `ChatUseCase` wiring: constructs `storage.Client()` only if
  `settings.history_gcs_uri` is set (avoids GCS's own eager ADC/credential
  resolution when running purely on local fallback), builds the
  `GcsHistoryLoader`, calls `.load()` once eagerly, stores the result on
  `app.state.professional_history`; deliberately no error handling — if
  loading fails, startup fails loudly, which is intentional since the whole
  app depends on this value, and no retry/refresh logic was added
- `pyproject.toml`, `docker/Dockerfile-backend` — added
  `"google-cloud-storage>=2.18,<3"` (same two places `redis` was added
  previously)
- `.env`, `.env.example` — added `HISTORY_LOCAL_PATH=` (empty), documenting
  the optional local-dev fallback path without enabling it
- `compose.prod.yaml` — mounted the whole `terraform/` directory (not just
  the key file) read-only into the backend service at `/secrets/terraform`,
  set `GOOGLE_APPLICATION_CREDENTIALS=/secrets/terraform/backend-sa-key.json`
  plus passthrough `HISTORY_GCS_URI`/`HISTORY_LOCAL_PATH` env entries;
  mounting the whole directory rather than the single key file is
  deliberate — `docker compose up` never fails to start even on a machine
  where the key hasn't been generated yet, and any resulting failure
  surfaces later, clearly, inside the app's own GCS-loading code instead of
  as an opaque Compose bind-mount error; reuses the SA key Terraform
  generated in the prior session, specifically for local Docker Compose dev
  (Cloud Run will attach the SA natively later and won't need a key)
- `tests/infrastructure/test_history_loader.py` — new; 8 tests covering the
  GCS branch (including correct bucket/blob-path splitting via mock
  assertions), the local-fallback branch (via a real `tmp_path` file), the
  "neither configured" `ValueError`, GCS taking priority over local fallback
  when both are set, and invalid `gs://` scheme handling

**Current stage**: Backend now loads the real professional-history markdown
from GCS at startup (or a local file in dev), verified end-to-end against
real infrastructure; still no LLM/Vertex AI call anywhere in the codebase,
so the loaded content isn't consumed by anything yet — it's just held in
`app.state.professional_history`, ready for the next step.

**Next steps**: Build the actual Vertex AI/Gemini call (infrastructure
layer) and wire `ChatUseCase` to build a prompt from
`app.state.professional_history` + the conversation, replacing the current
message-count placeholder response; define the Cloud Run service in
Terraform, attaching the `digital-twin-sa` service account natively (no key
needed there); `compose.test.yaml` / smoke-test infra still doesn't exist;
Redis-down resilience/error handling remains deferred; no retry/refresh
logic exists for the history load (deliberately, per the "load once at
startup, fail loudly" design).

---

## 2026-09-12 — Real Gemini/Vertex AI client with Redis-backed multi-turn memory

**Summary**: Closed the loop opened by the two prior same-day entries: the
candidate's professional history was already loading from GCS, and the
backend's GCP service account already had `roles/aiplatform.user` from
Terraform — this session wires a real `google-genai` Vertex AI client into
`ChatUseCase`, replacing the placeholder message-count response with a real
streamed Gemini answer grounded in that history, and backs the conversation
with real Redis-stored multi-turn memory. Scope grew through three user
corrections to the initial draft plan: (1) the plan started as single-shot
Q&A with no memory — corrected to wire Gemini to Redis too, so past turns
are actually considered, not just counted; (2) a configurable cap (default
10) was added on how many Q&A pairs get fed to Gemini, to bound the history
window; (3) backoff/retry on transient errors was added, reversing an
initial "no retry/error handling" stance. Verified directly against the
live model before any test-writing: confirmed the exact async SDK call
shape (`client.aio.models.generate_content_stream` returns a coroutine that
resolves to an async generator) by direct inspection — matched the planned
implementation with no changes needed; called `GeminiClient` directly with
a fabricated two-turn history and confirmed Gemini correctly recalled the
injected fact; tested the backoff logic with a mock raising twice then
succeeding (exactly 3 calls, correct recovery); then ran the full
`docker compose -f compose.prod.yaml up --build` stack and, through nginx,
asked a real question about the candidate's role/expertise (got a real,
history-grounded answer), a same-session follow-up asking it to repeat the
first question (correctly echoed verbatim, proving multi-turn memory works
over the real HTTP/SSE path), and a third request under a fresh
`session_id` (correctly had no memory of either prior exchange, and the
system prompt's scope guardrail correctly declined an out-of-scope probe
with no bleed-through). No backend errors in logs; stack torn down
afterward. The `python-test-writer` subagent then both added new test files
and substantially rewrote several existing ones, since `ChatUseCase`,
`RedisSessionStore`'s constructor, and the chat route's response shape all
changed in breaking ways; final result 57 tests passed, 100% coverage
across `backend/app` (158/158 statements), ruff clean, confirmed by
re-running the suite independently afterward.

**Files changed**:
- `backend/app/entities/chat_turn.py` — new; `ChatTurn` frozen dataclass
  (`role` — "user" or "model", Gemini's own vocabulary — and `text`)
- `backend/app/entities/prompts.py` — new; `SYSTEM_INSTRUCTION_TEMPLATE` +
  `render_system_instruction(professional_history)`; the system prompt
  constrains the agent to answer only from the candidate's professional
  history, decline out-of-scope questions (salary, availability, personal
  opinions) rather than guess, speak about the candidate in third person,
  and decline attempts to override these instructions (basic
  prompt-injection resistance); deliberately never templates the
  candidate's name, keeping the "never hardcode candidate data into source"
  guardrail intact
- `backend/app/infrastructure/gemini_client.py` — new; `GeminiClient`,
  constructor-injected `google.genai.Client` (the modern unified Google
  GenAI SDK with `vertexai=True`, not the older `vertexai` SDK), same
  injection style as `RedisSessionStore`/`GcsHistoryLoader`;
  `generate_stream(system_instruction, history, message)` builds a Gemini
  `contents` list from prior `ChatTurn`s plus the new message, keeping the
  history + scope rules in the separate `system_instruction` field rather
  than concatenated into the conversation; wraps only the stream-start call
  in backoff-with-retry (3 attempts, exponential backoff starting at 1s) —
  deliberately not mid-stream, since retrying after tokens have already
  reached the client would mean duplicating or dropping already-sent text
  with no clean way to do it at this layer; a failure after streaming
  begins still propagates and drops the connection as before
- `backend/app/persistence/session_store.py` — extended, not replaced:
  `RedisSessionStore` gained a third constructor arg `max_history_pairs`
  plus `append_turn` (RPUSH JSON-encoded `{role, text}`, sliding TTL
  refresh on every append, same pattern as the pre-existing message
  counter) and `get_history` (bounded `LRANGE` using Redis's own negative
  index range `-2*max_history_pairs` to `-1`, so only the most recent N
  pairs are fetched — bounding happens at the read, not by trimming the
  underlying list, which can still grow within the TTL window); the
  pre-existing `increment_message_count` counter was deliberately kept
  as-is rather than derived from the history list's length (already-working
  state, not worth refactoring for this task)
- `backend/app/entities/config.py` — added `gcp_project_id`,
  `vertex_location` (default "us-central1", matching the Terraform region
  default), `gemini_model` (default "gemini-2.5-flash"),
  `max_history_pairs` (default 10, from `MAX_HISTORY_PAIRS`)
- `backend/app/application/chat_use_case.py` — rewritten:
  `ChatUseCase.handle_message` is now an async generator (was a coroutine
  returning an int); increments the message counter, reads bounded history
  from Redis, streams Gemini's reply chunk-by-chunk to the caller while
  accumulating it, then — only after the stream completes successfully —
  persists both the user's turn and the full assembled model turn to Redis,
  so a failed/interrupted generation never pollutes history the next
  message would see (but that exchange is simply lost, not retried)
- `backend/app/presentation/api/chat.py` — rewritten to stream real chunks
  instead of the old fixed count; also fixes a real correctness bug: a
  Gemini chunk can contain embedded newlines, and the frontend's SSE parser
  expects multi-line payloads as repeated `data:`-prefixed lines within one
  frame — a naive `f"data: {chunk}\n\n"` would have silently corrupted any
  multi-line chunk. Fixed with a small helper that splits each chunk on
  `\n` and re-prefixes every line with `data: ` before the terminating
  blank line
- `backend/app/main.py` — lifespan reordered so history loads before
  `ChatUseCase` is constructed (it now needs the rendered system
  instruction); builds `genai.Client(vertexai=True, project=...,
  location=...)`, wraps it in `GeminiClient`; no new auth wiring needed —
  the same `GOOGLE_APPLICATION_CREDENTIALS`-mounted `digital-twin-sa` key
  already used for GCS also carries `roles/aiplatform.user` from Terraform
- `pyproject.toml`, `docker/Dockerfile-backend` — added
  `"google-genai>=1.0,<2"` (resolved to 1.75.0)
- `.env`, `.env.example`, `compose.prod.yaml` — added `GCP_PROJECT_ID`
  (real value `pmorandini-sandbox`, matching `terraform.tfvars`),
  `VERTEX_LOCATION`, `GEMINI_MODEL`, `MAX_HISTORY_PAIRS`, same
  `${VAR:-default}` pattern as every other backend env var
- `tests/entities/test_prompts.py`, `tests/infrastructure/test_gemini_client.py`
  — new; contents-building, role mapping, backoff retry-then-succeed,
  backoff give-up-and-reraise, falsy-chunk-text filtering, with
  `asyncio.sleep` patched so retry tests don't actually wait
- `tests/persistence/test_session_store.py`, `tests/entities/test_config.py`,
  `tests/application/test_chat_use_case.py` (including a dedicated test
  proving turns are appended only after the stream fully drains, not on a
  partial pull), `tests/api/test_chat.py` (including a dedicated test for
  the multi-line SSE framing fix), `tests/test_main.py` — all rewritten for
  the breaking constructor/response-shape changes; no dedicated test added
  for `ChatTurn` itself (plain dataclass, no logic, already exercised
  indirectly everywhere) — a deliberate, reasoned omission

**Current stage**: The digital-twin backend is now functionally complete
for its core loop — real Gemini answers, grounded in the real GCS-loaded
professional history, with real Redis-backed multi-turn memory bounded to a
configurable window, backoff on transient failures, all verified against
live GCP infrastructure end-to-end, fully unit-tested (57 passed, 100%
coverage, ruff clean).

**Next steps**: Define the Cloud Run service in Terraform (attaching
`digital-twin-sa` natively, no key needed there) — deferred since the first
Terraform entry, now the natural next step since the application itself is
functionally done; `compose.test.yaml` / smoke-test infra still doesn't
exist (real Redis TTL/ordering behavior and real SSE streaming wiring can
only be fully validated by smoke tests, not mocks); mid-stream Gemini
failures still drop the connection with no retry (deliberately, per the
backoff design); the underlying Redis conversation list is never trimmed
(`LTRIM`), only bounded at read time — fine for a short-lived demo session
bounded by TTL, worth revisiting if that stops being true; the system
prompt is explicitly a "first draft" and may need iteration once real usage
surfaces gaps in tone or scope-handling.
