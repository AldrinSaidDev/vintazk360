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

# Vendor Flowbite's runtime JS + Space Grotesk fonts into static/ so they can be
# served locally (no CDN) — the final image copies these out of the build stage.
RUN mkdir -p static/js static/fonts \
    && cp node_modules/flowbite/dist/flowbite.min.js static/js/flowbite.min.js \
    && cp node_modules/@fontsource/space-grotesk/files/space-grotesk-latin-400-normal.woff2 static/fonts/ \
    && cp node_modules/@fontsource/space-grotesk/files/space-grotesk-latin-500-normal.woff2 static/fonts/ \
    && cp node_modules/@fontsource/space-grotesk/files/space-grotesk-latin-700-normal.woff2 static/fonts/


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

# Bring in the compiled Tailwind stylesheet + vendored Flowbite JS from the build stage.
COPY --from=tailwind /build/static/css/output.css static/css/output.css
COPY --from=tailwind /build/static/js/flowbite.min.js static/js/flowbite.min.js
COPY --from=tailwind /build/static/fonts/ static/fonts/

EXPOSE 8000

# Default command runs the Django dev server. docker-compose overrides
# this with an entrypoint that waits for the DB and runs migrations first.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
