# ── Stage 1: builder ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: runtime ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="vagus-team" \
      description="Vagus Asistent — multi-model LLM agent system"

RUN groupadd -r vagus && useradd -r -g vagus -d /app -s /sbin/nologin vagus

WORKDIR /app

COPY --from=builder /install /usr/local

COPY src/ src/
COPY configs/ configs/
COPY scripts/ scripts/

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN chown -R vagus:vagus /app

USER vagus

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"]

CMD ["uvicorn", "vagus.layer3.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
