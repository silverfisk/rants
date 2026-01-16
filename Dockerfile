FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" "httpx>=0.27.0" "pydantic>=2.8.0" "pydantic-settings>=2.4.0" "pyyaml>=6.0.2" "aiosqlite>=0.20.0"

COPY gateway ./gateway
COPY config.yaml ./config.yaml

EXPOSE 8000

CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
