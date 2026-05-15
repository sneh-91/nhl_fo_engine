# HockeyOps AI

This repository is currently building toward `v0.5`.

Phase 5 currently includes:

- a FastAPI backend shell
- a React frontend shell
- centralized backend settings
- reusable NHL and CapWages source clients
- a canonical internal player schema
- cross-source identity matching and normalization rules
- deterministic backend tool methods for search, profile, contract, summary, and comparison
- an internal OpenAI Responses API orchestration layer over those tools
- one clear local startup path

The current build still does not include:

- a public Phase 6 query route

## Docs

Read these first:

1. `docs/README.md`
2. `docs/project-context.md`
3. `docs/v0.5-architecture.md`
4. `docs/v0.5-implementation-plan.md`

## Local Setup

### Backend

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

Run the backend from the `backend/` directory:

```powershell
Set-Location backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

Install dependencies and run Vite:

```powershell
Set-Location frontend
npm install
npm run dev
```

If needed, create `frontend/.env` from `frontend/.env.example`.

## Environment

Root `.env` is used for backend settings.

Current relevant backend variable:

- `CAPWAGES_API_KEY`

Optional backend variables:

- `FRONTEND_ORIGIN`
- `NHL_API_BASE_URL`
- `CAPWAGES_API_BASE_URL`
- `SOURCE_REQUEST_TIMEOUT_SECONDS`
- `MAX_PARALLEL_SOURCE_REQUESTS`
- `ROSTER_CACHE_TTL_SECONDS`
- `PLAYER_CACHE_TTL_SECONDS`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_REASONING_EFFORT`
- `OPENAI_MAX_TOOL_ROUNDS`
- `OPENAI_MAX_OUTPUT_TOKENS`

Frontend variables live in `frontend/.env` and currently include:

- `VITE_API_BASE_URL`

## Current Verification

Once both apps are running:

- backend health: `http://127.0.0.1:8000/api/health`
- frontend shell: `http://127.0.0.1:5173`

The frontend should display backend health information and the current phase boundary.

## Phase 5 Verification

Once `OPENAI_API_KEY` is present in the root `.env`, you can run:

```powershell
python scripts/test_phase5_orchestrator.py "Compare Aaron Ekblad vs Brandon Carlo"
```

Or try a discovery query:

```powershell
python scripts/test_phase5_orchestrator.py "Find right-shot defensemen on Florida under 7 million AAV"
```
