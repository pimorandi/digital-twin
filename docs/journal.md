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

---

## 2026-09-12 — Backend Dockerfile switched to uv, sourcing deps from pyproject.toml

**Summary**: The user noticed `docker/Dockerfile-backend` had its Python
dependencies hardcoded directly in a `pip install "fastapi>=...", ...` line,
duplicating the exact same list already declared in root `pyproject.toml`'s
`dependencies`. This duplication had been quietly growing all session —
every dependency added this session (`redis`, `google-cloud-storage`,
`google-genai`) required editing both places by hand, with nothing
enforcing they stayed in sync; a forgotten update in one place would only
have surfaced as a runtime `ImportError` inside the container. The user
asked directly: the backend container's package manager should be `uv`,
with dependencies imported from `pyproject.toml`. Rewrote the Dockerfile to
use Astral's official combined image `ghcr.io/astral-sh/uv:python3.12-
bookworm-slim` (replacing `python:3.12-slim` + pip), copying
`pyproject.toml` and `uv.lock` before `backend/app` (same cache-efficient
layer ordering as the existing frontend Dockerfile's `package*.json`
pattern) and running `uv sync --frozen --no-dev --no-install-project`. CMD
changed to `uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port
8000`. Flag rationale: `--frozen` uses `uv.lock` exactly as committed and
errors rather than silently re-resolving if it's stale — catches a
forgotten `uv lock` the same way the old duplication could have silently
shipped mismatched deps; `--no-dev` excludes the `dev` dependency group
(pytest, ruff, pytest-cov, and httpx as a dev dep) from the production
image; `--no-install-project` is needed because root `pyproject.toml` has
no `[build-system]` table — it's a plain dependency/tool-config manifest,
not a packaged library, so there's nothing to build/install as a project,
only dependencies to resolve; `--no-sync` on `uv run` at container start
avoids re-resolving/re-installing (and any network calls) every time the
container starts, since the environment was already built at image-build
time. Verified for real, in order: `docker compose -f compose.prod.yaml
build backend` succeeded on the first attempt with every flag working as
designed (no trial-and-error needed) — confirming the flag choices, made
from documentation/reasoning rather than a live test, held up against the
real installed uv version. Full stack brought up (`up -d`); backend logs
showed clean "Application startup complete" with no GCS/Vertex AI
credential regressions (nothing about env vars or the mounted `terraform/`
credentials changed, so this reverifies those integrations still work
through a differently-built image). Sent a real chat request through nginx
and got a real Gemini answer about the candidate, confirming the rebuilt
container actually serves traffic correctly, not just starts. Spot-checked
`docker compose exec backend uv pip list | grep -iE "pytest|ruff"` and
confirmed neither appears in the image — `httpx` does appear, but only as a
legitimate transitive runtime dependency of `google-genai`'s async client,
not leftover from the dev group, confirming `--no-dev` excluded the right
things. Stack torn down afterward. No application code was touched — this
was a build-mechanics-only fix, so no test-writer follow-up was needed
(Docker/build config isn't something the `python-test-writer` subagent
covers).

**Files changed**:
- `docker/Dockerfile-backend` — base image changed from `python:3.12-slim`
  to `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`; replaced the
  hardcoded `pip install "fastapi>=...", ...` line with `COPY pyproject.toml
  uv.lock ./` followed by `RUN uv sync --frozen --no-dev
  --no-install-project`; `CMD` changed from plain `uvicorn ...` to `uv run
  --no-sync uvicorn ...`

**Current stage**: Same functional state as the prior entry (Gemini/Vertex
AI wired with Redis-backed multi-turn memory, fully tested) — this entry is
purely an infrastructure/build-hygiene fix, closing out the
dependency-duplication issue between `pyproject.toml` and the backend
Dockerfile that had been accumulating risk since the very first
backend-skeleton task.

**Next steps** (carried forward, still open): Define the Cloud Run service
in Terraform, attaching `digital-twin-sa` natively; `compose.test.yaml` /
smoke-test infra still doesn't exist; mid-stream Gemini failures still drop
the connection with no retry (deliberate); the underlying Redis
conversation list is never trimmed, only bounded at read time; the system
prompt is a first draft that may need iteration.

---

## 2026-09-13 — Cloud Run deployment via Cloud Build, then locked back down

**Summary**: Picked up the prior entries' open "next step" and assembled
everything already built (the `digital-twin-sa` service account with GCS/
Vertex AI access, the backend loading real history and calling real Gemini
with Redis-backed memory, and the prod/test Compose split whose whole
premise was "Cloud Run provides credentials natively, no JSON key") into an
actual live deployment. The user, when asked to weigh in, chose Cloud Build
(building in GCP, pushing to Artifact Registry) over building/pushing
locally. This surfaced one real design bug and two real deployment bugs
that only showed up once the app was actually running on Cloud Run, not
during design: `docker/nginx.conf` hardcoded `set $backend_upstream
backend:8000;`, a Compose-only service-name DNS lookup — Cloud Run's
multi-container sidecars share one network namespace and talk over
`localhost`, so nginx would never have reached the backend. Fixed by
renaming the file to `docker/nginx.conf.template`, parameterizing the host
as `${BACKEND_UPSTREAM}`, and using nginx's built-in template feature
(`/etc/nginx/templates/*.template` gets envsubst'd into
`/etc/nginx/conf.d/` at container start); `docker/Dockerfile-ui` now copies
there instead of to a static conf file, and `compose.prod.yaml`'s frontend
service gained `BACKEND_UPSTREAM: backend` so the same image works
unchanged on both Compose (`backend`) and Cloud Run (`127.0.0.1`). Verified
locally first by rendering the substituted config inside the running
frontend container and confirming a real chat request through nginx still
worked, before trusting it on Cloud Run. Added a new root `cloudbuild.yaml`
(two `docker build` steps for frontend/backend, images pushed automatically
via the top-level `images:` list — no explicit push steps needed); `redis`
isn't built or mirrored at all, since Cloud Run can pull `redis:7-alpine`
straight from Docker Hub. Extended `terraform/main.tf`/`variables.tf`/
`outputs.tf` with the Cloud Run/Artifact Registry/Cloud Build APIs, an
Artifact Registry Docker repository, an explicit IAM grant for Cloud
Build's own service agent (rather than assuming default permissions), and
`google_cloud_run_v2_service.app` with three sidecar containers (nginx,
backend, redis) — the backend container gets only the env vars that must
differ from `load_settings()`'s own defaults (`GCP_PROJECT_ID`,
`VERTEX_LOCATION`, `HISTORY_GCS_URI`, `REDIS_URL=redis://localhost:6379/0`),
everything else deliberately left unset — and
`template.service_account = google_service_account.backend.email`, the
actual payoff of the earlier "no JSON key on Cloud Run" design decision.
Two more real bugs were found only by deploying and reading live logs, not
guessed in advance: (1) attaching a service account to Cloud Run wasn't
enough on its own — Cloud Run's own service agent needed
`roles/iam.serviceAccountUser` granted *on* `digital-twin-sa` before it
could mint tokens for it, otherwise every GCS/Vertex AI call 403'd at the
metadata-server level; fixed with a new
`google_service_account_iam_member.run_agent_can_act_as_backend` resource,
diagnosed via `gcloud logging read`. (2) `google_cloud_run_v2_service`
defaults `deletion_protection = true`; a first failed creation attempt left
the resource tainted in state, needing `terraform untaint` +
`terraform apply -replace=...` before it could be recreated — resolved by
adding `deletion_protection = false` explicitly, with a comment noting this
is a low-traffic demo service. (3) A real ordering dependency not visible
in the Terraform graph alone: Artifact Registry must exist before Cloud
Build can push, but Cloud Run's service definition can't apply until the
images already exist in the registry — so a single `terraform apply`
doesn't work from scratch; resolved by applying the registry+IAM piece
first with `-target=...`, then `gcloud builds submit`, then the full
apply. Verified end-to-end against the real live deployment (not local
Compose): a real question through the live URL got a real, history-
grounded Gemini answer, and a same-session follow-up asking what was just
asked correctly recalled the prior turn, proving Redis-sidecar multi-turn
memory works over `localhost` on actual Cloud Run. A
`google_cloud_run_v2_service_iam_member.public_invoker` binding for
`allUsers` was then added (required for Cloud Run's default-private
services to be reachable at all) and, in a same-day follow-up, intentionally
removed again after the user pointed out the app is still in testing — the
resource block was replaced with a comment explaining how to re-add it once
nginx is meant to be public per `docs/architecture.md`. Verifying the
removal had a real surprise: IAM propagation for Cloud Run's invoker check
took over a minute — an initial `curl` right after `terraform apply` still
returned 200 on both the homepage and the dynamic `/api/chat/stream` POST
(ruling out a caching explanation), and only after polling for a couple of
minutes did both start correctly returning 403. Explicitly out of scope,
per the plan discussed with the user beforehand: a push-triggered
`google_cloudbuild_trigger` (no git remote exists yet — revisit once one
does; `cloudbuild.yaml` itself wouldn't need to change), image tagging
beyond `:latest`, resource sizing/autoscaling tuning, Memorystore instead
of the redis sidecar (would break the per-instance architecture the app is
built around), a custom domain, and CI on push.

**Files changed**:
- `docker/nginx.conf` → `docker/nginx.conf.template` — renamed; hardcoded
  `backend:8000` replaced with `${BACKEND_UPSTREAM}` for nginx's built-in
  envsubst templating
- `docker/Dockerfile-ui` — now copies the template into
  `/etc/nginx/templates/` instead of a static `conf.d` file
- `compose.prod.yaml` — frontend service gained `BACKEND_UPSTREAM: backend`
  runtime env var
- `cloudbuild.yaml` — new; builds and pushes the frontend and backend
  images to Artifact Registry
- `terraform/main.tf` — added `google_project_service` for
  `run.googleapis.com`/`artifactregistry.googleapis.com`/
  `cloudbuild.googleapis.com`; `google_artifact_registry_repository.images`;
  `data "google_project" "current"`; IAM grant for Cloud Build's service
  agent; `google_cloud_run_v2_service.app` (nginx/backend/redis sidecar
  containers, `deletion_protection = false`, backend service account
  attached); `google_service_account_iam_member
  .run_agent_can_act_as_backend`; a public-invoker binding added then
  replaced with a comment explaining how to restore it
- `terraform/variables.tf`, `terraform/outputs.tf` — supporting variables/
  outputs for the above (repository name/location, Cloud Run service name,
  live service URL)
- `compose.test.yaml` — new (referenced by this session's setup; smoke-test
  infra itself remains a separate open item)

**Current stage**: The digital twin app has a real, working Cloud Run
deployment (verified end-to-end including multi-turn memory) but is
currently locked to authenticated-only access while testing continues, not
publicly reachable.

**Next steps**: Re-grant the `allUsers` invoker binding when ready to go
public (the commented-out block in `terraform/main.tf` shows exactly what
to restore); consider an image tagging strategy beyond `:latest` if
redeploy-on-push ever matters; connect a git remote and revisit a
push-triggered Cloud Build trigger; `compose.test.yaml` / smoke-test infra
still doesn't exist; mid-stream Gemini failures still drop the connection
with no retry; the system prompt is still a first draft.

---

## 2026-09-19 — Durable chat logging to GCS, Redis list now trimmed

**Summary**: Resolves the "Redis conversation list is never trimmed
(`LTRIM`)" next-step from the 2026-09-12 Gemini/Redis entry (that entry is
left untouched as history). The concern was real: LLM context was bounded at
read time (`LRANGE` of the last `2 * MAX_HISTORY_PAIRS`), but the list itself
grew forever and the TTL resets on every write, so an active or abusive
session could grow Redis memory unbounded. The session store now does
`RPUSH` + `LTRIM` + `EXPIRE` in a single pipeline.

Trimming discards old turns, so we also added durable chat logging into the
same private history bucket under a `chat-logs/` prefix. Design decisions:
GCS objects are immutable, so each exchange (user + model message) is its
own JSON object, written create-only (`if_generation_match=0`, an HTTP 412
is treated as success so retries are idempotent). Path is
`chat-logs/<YYYY-MM-DD>/<session_id>/<utc_ts>_<seq:05d>.json`. Each exchange
is logged immediately rather than batched on Redis overflow, so an instance
dying loses nothing. The upload is awaited inside the request via
`asyncio.to_thread` because Cloud Run throttles CPU once the response ends;
failures are logged and never break the chat. Client IP is deliberately not
logged (user decision). `session_id` is now validated in the request schema
(`^[A-Za-z0-9_-]{1,64}$`) since it becomes part of an object path. Retention
is 90 days via a bucket lifecycle rule scoped to the prefix. Chat logging is
optional: enabled only when `CHAT_LOG_GCS_URI` is set.

**Files changed**:
- `backend/app/entities/chat_log_record.py` — new; record type for one logged exchange
- `backend/app/infrastructure/chat_log_writer.py` — new; `GcsChatLogWriter` (create-only upload, path building)
- `backend/app/application/chat_use_case.py` — optional writer injected; `_log_exchange` after each reply
- `backend/app/persistence/session_store.py` — pipeline with `RPUSH` + `LTRIM` + `EXPIRE`
- `backend/app/entities/config.py` — optional `CHAT_LOG_GCS_URI`
- `backend/app/main.py` — GCS client built if history or chat-log URI set; writer wired in
- `backend/app/presentation/schemas/chat.py` — `session_id` pattern constraint
- `backend/app/infrastructure/history_loader.py` — `_parse_gcs_uri` made public as `parse_gcs_uri` for reuse
- `.env.example` — documents `CHAT_LOG_GCS_URI`
- `docs/architecture.md` — new "Chat logs" section
- `terraform/main.tf` — `objectCreator` IAM member with prefix condition, lifecycle rule (delete after `chat_log_retention_days` on `chat_log_prefix`), `CHAT_LOG_GCS_URI` env on backend container, added to Cloud Run `depends_on`
- `terraform/variables.tf` — `chat_log_prefix`, `chat_log_retention_days` (90)
- `tests/infrastructure/test_chat_log_writer.py` — new unit tests for the writer
- `tests/smoke/test_chat_log_writer_smoke.py` — new; skipped unless `SMOKE_BUCKET` is set
- `tests/persistence/test_session_store.py`, `tests/application/test_chat_use_case.py`, `tests/entities/test_config.py`, `tests/test_main.py`, `tests/api/test_chat.py`, `tests/infrastructure/test_history_loader.py` — updated for the above

**Current stage**: Code is complete and locally verified (ruff clean, pytest
93 passed / 1 skipped, 100% backend coverage, `terraform validate` OK), but
nothing is applied or deployed yet and all changes are uncommitted on
`feature/remote-saving`.

**Next steps**: Run `terraform plan`/`apply` (expect the IAM member, lifecycle
rule, and env var); rebuild and redeploy the backend image; send chats and
verify objects appear under `gs://<bucket>/chat-logs/`; run the smoke test
with `SMOKE_BUCKET` set. Consider logging partial replies on mid-stream
disconnects (try/finally with a partial flag), a UI privacy notice for logged
chats, and a BigQuery external table for querying logs. Still open from
earlier entries: `allUsers` invoker re-grant, image tagging beyond
`:latest`, push-triggered Cloud Build trigger, Gemini mid-stream failure
retry, and the first-draft system prompt.
