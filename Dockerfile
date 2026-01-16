FROM python:3.13-slim

WORKDIR /app

COPY --chown=1000:1000 pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" "httpx>=0.27.0" "pydantic>=2.8.0" "pydantic-settings>=2.4.0" "pyyaml>=6.0.2" "aiosqlite>=0.20.0"

COPY --chown=1000:1000 gateway ./gateway
COPY --chown=1000:1000 config.yaml ./config.yaml

# Create user "rants"
RUN groupadd -g 1000 rants && \
    useradd -u 1000 -g rants -s /bin/bash -m rants && \
    chown -R rants:rants .

USER rants

EXPOSE 8000

CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
