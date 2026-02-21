FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY configs/ configs/
COPY dashboard/ dashboard/
COPY alembic.ini .
COPY alembic/ alembic/

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# --- API ---
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "vagus.layer3.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Dashboard ---
FROM base AS dashboard
RUN pip install --no-cache-dir streamlit>=1.30
EXPOSE 8501
CMD ["streamlit", "run", "dashboard/main.py", "--server.port", "8501", "--server.address", "0.0.0.0"]

# --- Telegram Bot ---
FROM base AS telegram
RUN pip install --no-cache-dir aiogram>=3.0
CMD ["python", "-c", "import asyncio; from vagus.layer3.channels.telegram.bot import start_telegram_bot; asyncio.run(start_telegram_bot())"]
