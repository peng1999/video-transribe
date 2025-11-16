# Repository Guidelines

## Project Structure & Module Organization
- `backend/app/` — FastAPI code (`main.py`, `worker.py`, `models.py`, `schemas.py`, `db.py`).
- `backend/requirements.txt` — backend Python dependencies.
- `frontend/` — React + Vite app (`src/` components, pages, API helper). Build output lives in `frontend/dist`.
- `.env.example` — sample backend configuration; copy to `backend/.env` with real keys.
- `README.md` — quickstart; read alongside this guide.

## Build, Test, and Development Commands
- Backend (from `backend/`):
  - `python -m venv .venv && source .venv/bin/activate` — create/activate venv.
  - `pip install -r requirements.txt` — install dependencies.
  - `uvicorn app.main:app --reload --port 8000` — run API with auto-reload.
- Frontend (from `frontend/`):
  - `npm install` — install JS deps.
  - `npm run dev -- --host` — start Vite dev server with API proxy.
  - `npm run build` — production build to `dist/`.

## Coding Style & Naming Conventions
- Python: keep functions small; prefer `async` for IO paths; follow PEP8 (4-space indent). Use clear stage names matching `JobStatus` enum.
- TypeScript/React: functional components with hooks; camelCase for variables/functions; PascalCase for components; prefer inline styles kept minimal.
- Filenames: snake_case for Python modules, PascalCase for React components. Env vars uppercase with underscores.

## Testing Guidelines
- No automated suites yet. When adding tests:
  - Backend: prefer `pytest`; place under `backend/tests/` mirroring module paths.
  - Frontend: prefer `vitest` + `@testing-library/react`; place under `frontend/src/__tests__/`.
  - Aim to cover job lifecycle (download → transcribe → format) and WebSocket progress events.

## Commit & Pull Request Guidelines
- Commits: concise imperative subject (e.g., "Add streaming formatter"), keep related changes together.
- Pull Requests should include: summary of changes, testing performed (`npm run build`, `uvicorn` smoke), screenshots/GIFs for UI changes, and any follow-up TODOs.

## Security & Configuration Tips
- Never commit real API keys. Use `backend/.env` locally and deployment secrets in CI/hosting.
- Requires `ffmpeg` on host for yt-dlp; document install if not present.
- Validate user input: current API restricts to `bilibili.com` URLs; keep or extend carefully.
