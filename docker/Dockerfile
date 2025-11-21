# Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend .
RUN npm run build

# Backend image (uv project)
FROM python:3.13-slim AS backend
ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates && rm -rf /var/lib/apt/lists/*
# install uv
RUN pip install --no-cache-dir uv

# copy metadata and minimal package stub so uv editable install succeeds
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/app/__init__.py ./app/__init__.py
RUN uv sync --frozen --no-dev
ENV PATH="/app/backend/.venv/bin:${PATH}"

# copy full source after deps are cached
COPY backend/app ./app

# copy built frontend for potential static serving (not used by nginx container)
COPY --from=frontend /app/frontend/dist ../frontend/dist

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Serve frontend with nginx and proxy /api to backend
FROM nginx:1.27-alpine AS frontend-nginx
COPY --from=frontend /app/frontend/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
