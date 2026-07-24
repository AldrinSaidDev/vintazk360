# syntax=docker/dockerfile:1

# ---- Base image ----
FROM python:3.13-slim AS base

# Keep Python from writing .pyc files and buffering stdout/stderr.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps: libpq for psycopg (runtime), build tools kept minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# ---- Python dependencies (cached layer) ----
# Copy only the requirements first so this layer is cached until deps change.
COPY requirements.txt .
COPY requirements/ requirements/
RUN pip install -r requirements/prod.txt

# ---- Application code ----
COPY . .

EXPOSE 8000

# Default command runs the Django dev server. docker-compose overrides
# this with an entrypoint that waits for the DB and runs migrations first.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
