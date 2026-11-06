# The API. Build context is the repo root (app/), see docker-compose.yml.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/srv/api/.venv/bin:$PATH"
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv
WORKDIR /srv/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --extra local-ai
COPY api/alembic.ini ./
COPY api/migrations ./migrations
COPY api/app ./app
EXPOSE 8000
# bring the database up to date, then serve
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
