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
