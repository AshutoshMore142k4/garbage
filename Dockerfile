FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

COPY . .

# Render (and most container platforms) inject $PORT at runtime and health-check that exact
# port -- a hardcoded port here would make the container start successfully while the health
# check fails forever, since Render's own probe wouldn't be looking at 8000. Falls back to 8000
# for local `docker run` with no PORT set. Shell form so $PORT is expanded; exec form (the JSON
# array syntax) does not perform variable substitution.
CMD uvicorn ledgerguard.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
