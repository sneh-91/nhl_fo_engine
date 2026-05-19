# HockeyOps AI 🏒

HockeyOps AI is a local NHL front-office assistant. Ask hockey ops questions in the browser and get concise answers backed by structured data from NHL API, CapWages,  MoneyPuck.com, and manual team-context data.


## What It Does

- Answers NHL player, roster, contract, team, and comparison questions through `POST /api/ask`.
- Uses OpenAI Responses API orchestration over deterministic backend tools.
- Merges NHL profile/stats data, CapWages contract data, MoneyPuck analytics, and verified team context.
- Supports skaters, goalies, player search, leaderboards, team summaries, and player-vs-player comparisons.
- Shows both the prose answer and clean supporting data cards/tables in the React UI.

## Stack

- Backend: FastAPI, Pydantic, HTTPX, OpenAI Python SDK
- Frontend: React, TypeScript, Vite
- Data: NHL API, CapWages API, local MoneyPuck CSVs, local team-context JSON

## Project Layout

```text
backend/    FastAPI app, clients, orchestration, normalized tool services
frontend/   React/Vite app and visual support-data renderers
data/       Local MoneyPuck datasets and manual team context
docs/       Current architecture notes
scripts/    API and source-client smoke tests
```

## Setup

Create a root `.env` from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Required values:

- `OPENAI_API_KEY`
- `CAPWAGES_API_KEY`

Optional frontend override:

```powershell
Set-Content frontend/.env "VITE_API_BASE_URL=http://127.0.0.1:8000"
```

## Run Locally

Backend:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
Set-Location backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## Verify

- API health: `http://127.0.0.1:8000/api/health`
- Orchestrator diagnostics: `http://127.0.0.1:8000/api/diagnostics/orchestrator`
- Frontend: `http://127.0.0.1:5173`

CLI smoke test:

```powershell
python scripts/test_phase6_api.py "Compare Aaron Ekblad vs Brandon Carlo"
```

Try these in the UI:

- `Find right-shot defensemen on Florida under 7 million AAV`
- `Who is better, Brandon Carlo or Bowen Byram? Pick one and defend your stance!`
- `Who leads the NHL in goalie wins?`
- `Were the Toronto Maple Leafs good this year?`

## Docs

Start with:

1. `docs/v0.5-architecture.md`
2. `docs/nhl-rules-rag-rollout.md`
3. `docs/nhl-rules-rag-stage-1-plan.md`
4. `docs/nhl-rules-rag-stage-2-plan.md`

## Current Limits

- Focused on NHL/hockey-ops questions only.
- Search is built around the current active NHL roster universe.
- Answers are limited to available NHL API, CapWages, local MoneyPuck, and local team-context coverage.
- Broader validation and polish are still ongoing.
