FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

COPY . .

CMD ["uvicorn", "ledgerguard.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
