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
