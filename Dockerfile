# syntax=docker/dockerfile:1

# ---- Tailwind build stage ----
# Compiles static/css/output.css from the templates + input.css. Node lives
# only in this stage and never ships in the final runtime image.
FROM node:22-slim AS tailwind

WORKDIR /build

# Install JS deps (cached until package.json changes).
COPY package.json package-lock.json* ./
RUN npm install

# Copy the sources Tailwind needs to scan, then build the stylesheet.
COPY tailwind.config.js ./
COPY static/ static/
COPY templates/ templates/
COPY apps/ apps/
RUN npm run build:css


# ---- Base Python image ----
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

# Bring in the compiled Tailwind stylesheet from the build stage.
COPY --from=tailwind /build/static/css/output.css static/css/output.css

EXPOSE 8000

# Default command runs the Django dev server. docker-compose overrides
# this with an entrypoint that waits for the DB and runs migrations first.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
