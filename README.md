# HockeyOps AI

This repository is currently building toward `v0.5`.

Phase 1 sets up only:

- a FastAPI backend shell
- a React frontend shell
- centralized backend settings
- one clear local startup path

Phase 1 does not include:

- NHL API client integration
- CapWages client integration
- tool calling
- model orchestration

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

Frontend variables live in `frontend/.env` and currently include:

- `VITE_API_BASE_URL`

## Phase 1 Verification

Once both apps are running:

- backend health: `http://127.0.0.1:8000/api/health`
- frontend shell: `http://127.0.0.1:5173`

The frontend should display backend health information and the current Phase 1 boundary.
