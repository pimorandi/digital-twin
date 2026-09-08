# CLAUDE.md

## Overview

This repo runs a chat-based "digital twin": an LLM agent that answers recruiters'
questions about a candidate's professional experience. The candidate's history is
stored in a markdown file and exposed to the agent llmwiki-style (the agent reads
and reasons over the markdown rather than a vector store).

## Architecture

Three containers orchestrated by Docker Compose:

- **frontend** — Vite + React + TypeScript, styled with Tailwind CSS. Chat UI,
  consumes the backend over SSE for token streaming.
- **backend** — FastAPI (Python 3.12) served by uvicorn. Hosts the agent, calls
  the LLM on GCP, streams responses to the frontend via SSE.
- **redis** — holds the state of the *ongoing* chat only (conversation history for
  a single session).

## Statelessness

Deployed to GCP Cloud Run. Every instance starts with no memory of any past chat.
Session state is per-instance and ephemeral by design:

- Redis state is in-memory, per-instance — NOT a shared/managed instance.
- Sessions carry a TTL and expire after inactivity, so abandoned chats don't
  accumulate and exhaust instance memory. (Recruiters typically close the tab
  mid-chat, so expiry is important, not optional.)
- Do not add logic that assumes state survives across instances or restarts.

## LLM / agent

- LLM runs on GCP.
- Responses stream to the client via SSE.
- The candidate's professional history lives in a markdown file (see guardrails).
  The agent reads this as its knowledge source — no vector store / embeddings.

## Repository layout

Frontend, backend, and shared config all live at the top level of the repo:

  - /frontend Vite + React + TS app
  - /backend FastAPI app
  - <shared config> docker-compose.yml, .env, etc. at repo root


## Local development

- `docker compose up` starts and orchestrates all three containers locally.
- Configuration is supplied via a `.env` file at the repo root. Keep a `.env.example` documenting every required variable (without values).

## Testing & quality

- **Backend tests:** pytest.
- **Frontend tests:** Vitest + React Testing Library.
- **Linting:** ruff (backend). ESLint + Prettier (frontend).

Before considering any task done, always:
1. Run the linters.
2. Run the tests.
Both must pass.

## Conventions

- All code, comments, and commit messages in English.

## Guardrails — never do these

- **Never commit `.env`** or any secret it contains.
- **Never commit the markdown file containing the candidate's professional
  history.** (Add both to `.gitignore`.)
- Never break the stateless assumption (see Statelessness).
- Never hardcode the candidate's data into source — it comes from the markdown
  file / config only.