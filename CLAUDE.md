# CLAUDE.md

## Overview

This repo runs a chat-based "digital twin": an LLM agent that answers recruiters'
questions about a candidate's professional experience. The candidate's history is
stored in a markdown file and exposed to the agent llmwiki-style (the agent reads
and reasons over the markdown rather than a vector store).

## Architecture (essentials)

Single Cloud Run service, deployed stateless. Load-bearing facts that constrain
work across the repo:

- **One public entry point: nginx.** nginx serves the static React build and
  reverse-proxies `/api` to the backend. Nothing else is internet-facing.
- **Backend and redis are never exposed** — they are reachable only from nginx
  over the internal network.
- **Frontend calls relative `/api`** — never a Compose service hostname
  (`http://backend:8000` is unreachable from the browser).
- **Stateless per instance.** Every instance starts with no memory of any past
  chat; nothing may assume state survives across instances or restarts.

Full request flow, the single-entry-point rationale, and history-file loading:
**read `docs/architecture.md` before changing anything about routing, the
nginx/backend boundary, session state, or how the professional history is loaded.**

## Backend code organization (clean architecture)

Backend code follows a layered clean-architecture pattern. Every new class or
module belongs to exactly one layer:

- **entities** — data types, domain classes, templates, and shared utilities
  (logger, config helpers). No business logic, no I/O.
- **infrastructure** — classes that manage external services (LLM client, GCS, etc.).
- **persistence** — code that manages data storage and retrieval (redis clients).
- **application** — business logic: the use cases and orchestration that define
  what the system does.
- **presentation** — API endpoints and DTO (data transfer object) definitions.

**Dependency direction:** dependencies point inward. `presentation`,
`application`, and `persistence` may depend on `infrastructure` and `entities`;
`infrastructure` may depend on `entities` only; `entities` depends on nothing else in
the backend. Never import a presentation/infrastructure/persistence detail into 
`entities` — depend on an abstraction instead.

When adding backend code, place it in the correct layer and respect the dependency
direction. If a change seems to need an inward layer importing an outward one, that
is a design smell — surface it rather than working around it.

## Components

Orchestrated by Docker Compose:

- **frontend** — Vite + React + TypeScript, Tailwind CSS. Chat UI, consumes the
  backend over SSE for token streaming. Served as a static build by nginx.
- **nginx** — public entry point; serves the frontend and proxies `/api`.
- **backend** — FastAPI (Python 3.12) on uvicorn. Hosts the agent, calls the LLM
  on GCP, streams responses via SSE.
- **redis** — holds the state of the *ongoing* chat only (single session),
  in-memory and per-instance, with a TTL so abandoned sessions expire.

## Repository layout

Frontend, backend, and shared config all live at the top level of the repo:

    /frontend        Vite + React + TS app
    /backend         FastAPI app
    /docker          Dockerfiles + nginx.conf
    /docs            architecture.md
    <shared config>  compose.prod.yaml, compose.test.yaml, .env, etc. at repo root

## Local development

- Every service declares `profiles: ["prod", "test"]`, so a `--profile` flag is
  required — plain `docker compose -f compose.prod.yaml up` now starts nothing.
- `docker compose -f compose.prod.yaml --profile prod up` starts the prod-shaped
  stack: matches what Cloud Run will actually run (backend has no JSON
  credentials — Cloud Run provides ADC via the attached service account
  instead). GCS/Vertex AI calls will fail locally under this profile; that's
  expected, not a bug.
- `docker compose -f compose.prod.yaml -f compose.test.yaml --profile test up`
  starts the same stack with `compose.test.yaml` overriding `backend` to mount
  the Terraform-generated service-account key, so GCS/Vertex AI actually work
  locally. Use this for local testing and for smoke tests once they exist.
- Configuration is supplied via a `.env` file at the repo root. Keep a
  `.env.example` documenting every required variable (without values).

## Testing & quality

### Backend

Two sets of tests, both pytest:

- **Unit tests** — quick, isolated checks of object initialization and standalone
  methods/functions. Use mocks to emulate other resources (Redis, LLM, GCS). No
  external services required.
- **Smoke tests** — exercise the actual classes against a real environment, set up
  via `compose.test.yaml`. Heavier; require the test containers to be running.

Linting is ruff.

### Frontend

Vitest + React Testing Library are available but not required. Frontend tests are
optional and encouraged only for genuinely stateful logic (e.g. SSE token
accumulation, dropped-connection handling) — not routine component rendering.
Linting is ESLint + Prettier.

### Quality gate

Before considering any task done:
1. Run ruff and pytest — unit tests at minimum; smoke tests when the change
   touches integration behavior. Both must pass.
2. Frontend tests run if present, but are not a blocking gate.

## Conventions

- All code, comments, and commit messages in English.

## Guardrails — never do these

- **Never commit `.env`** or any secret it contains.
- **Never commit the professional-history markdown file** (gitignored; loaded at
  runtime from a private GCS bucket). **Never make that bucket public.**
- **Never expose the backend or redis to the internet** — nginx is the only public
  entry point.
- **Never break the stateless assumption** (see Architecture essentials).
- **Never hardcode the candidate's data into source** — it comes from the GCS-loaded
  markdown / config only.