# My digital-twin

A chat-based digital twin: an LLM agent that answers recruiters' questions
about a candidate's professional experience.

## Overview

The candidate's history lives in a markdown file and is exposed to the agent
llm-wiki-style — the agent reads and reasons over the markdown directly rather
than through a vector store. The file is never committed to the repo; it's
loaded at runtime from a private GCS bucket.

## Architecture

A single, stateless Cloud Run service: nginx is the only public entry point,
serving the React frontend and reverse-proxying `/api` to a FastAPI backend,
which streams LLM responses over SSE. A Redis sidecar holds only the state of
the ongoing chat, with a TTL so abandoned sessions expire.

See [docs/architecture.md](docs/architecture.md) for the full request flow,
the single-entry-point rationale, and how the history file is loaded.

## Components

- **frontend** — Vite + React + TypeScript, Tailwind CSS. Chat UI, consumes
  the backend over SSE for token streaming.
- **nginx** — public entry point; serves the frontend and proxies `/api`.
- **backend** — FastAPI (Python 3.12) on uvicorn. Hosts the agent, calls the
  LLM on GCP, streams responses via SSE.
- **redis** — holds the state of the *ongoing* chat only (single session),
  in-memory and per-instance, with a TTL so abandoned sessions expire.

## Local development

Copy `.env.example` to `.env` and fill in the required values.

Every service declares `profiles: ["prod", "test"]`, so a `--profile` flag is
required:

```
docker compose -f compose.prod.yaml --profile prod up
```

Matches what Cloud Run actually runs. GCS/Vertex AI calls will fail locally
under this profile — that's expected, since the backend relies on Cloud Run's
attached service account (ADC) instead of a JSON key.

```
docker compose -f compose.prod.yaml -f compose.test.yaml --profile test up
```

Same stack, but `compose.test.yaml` mounts a Terraform-generated
service-account key so GCS/Vertex AI actually work locally. Use this for local
testing and smoke tests.

## Deployment

Every push to `master` is tested, built and deployed to Cloud Run by the
`deploy-on-master` Cloud Build trigger. See the "Deployment" section in
[docs/architecture.md](docs/architecture.md) for the pipeline and one-time setup.

## Testing & quality

Backend:

```
ruff check .
pytest
```

Unit tests mock external services (Redis, LLM, GCS) and run without any
containers. Smoke tests exercise the real classes against the `test` profile
stack above.

Frontend tests (Vitest + React Testing Library) are optional, encouraged only
for genuinely stateful logic.

## Repository layout

```
/frontend        Vite + React + TS app
/backend         FastAPI app
/docker          Dockerfiles + nginx.conf
/docs            architecture.md
/terraform       infrastructure as code
<shared config>  compose.prod.yaml, compose.test.yaml, .env, etc. at repo root
```
