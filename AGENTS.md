# Repository Guidelines

## Project Structure & Module Organization
- `backend/app/` — FastAPI code (`main.py`, `worker.py`, `models.py`, `schemas.py`, `db.py`).
- `backend/pyproject.toml` / `uv.lock` — uv-managed backend dependencies; `.venv` created by `uv sync`.
- `frontend/` — React + Vite app (`src/` components, pages, API helper). Build output lives in `frontend/dist`.
- `.env.example` — sample backend configuration; copy to `backend/.env` with real keys.
- `README.md` — quickstart; read alongside this guide.

## Build, Test, and Development Commands
- Backend (from `backend/`):
  - `uv sync` — install deps into `.venv` (uses `pyproject.toml`).
  - `uv run uvicorn app.main:app --reload --port 8000` — run API with auto-reload via uv-managed venv.
  - `uv run black app` — Python 格式化。
- Frontend (from `frontend/`):
  - `npm install` — install JS deps.
  - `npm run dev -- --host` — start Vite dev server with API proxy.
  - `npm run build` — production build to `dist/`.
  - `npm exec prettier -- --write "src/**/*.{ts,tsx,js,jsx}"` — 前端格式化（使用 nvm 提供的最新版 Prettier）。
  - `npx tsc --noEmit` — 类型检查（使用 `.nvmrc` 指定的 Node 版本，如 `v25.2.0`）。

## Node 版本
- 项目根目录提供 `.nvmrc`，版本 `v25.2.0`。建议执行 `nvm use` 后再运行前端命令，确保与工具链版本匹配。若使用 fish，**优先**运行 `fish -c 'nvm use'`（自动定位 nvm 安装路径）；仅在特殊场景下再手动设置 `set -x PATH ~/.local/share/nvm/v25.2.0/bin $PATH` 作为备用方案。

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
