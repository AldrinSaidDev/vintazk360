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

# Vendor the fonts, Font Awesome and Chart.js into static/ so they can be served
# locally (no CDN) — the final image copies these out of the build stage.
#
# These are gitignored, so on a build host that clones the repo (Render) they do
# NOT arrive with the source: this stage is the only thing that puts them in the
# image. Keep the list in step with the `tailwind` service in docker-compose.yml.
RUN mkdir -p static/fonts static/fontawesome/css static/fontawesome/fonts static/vendor \
    && for w in 300 400 500 700; do cp node_modules/@fontsource/space-grotesk/files/space-grotesk-latin-$w-normal.woff2 static/fonts/; done \
    && for w in 100 200 300 400 500 600 700; do cp node_modules/@fontsource/montserrat/files/montserrat-latin-$w-normal.woff2 static/fonts/; done \
    && cp node_modules/font-awesome/css/font-awesome.min.css static/fontawesome/css/ \
    && cp node_modules/font-awesome/fonts/* static/fontawesome/fonts/ \
    && cp node_modules/chart.js/dist/chart.umd.js static/vendor/chart.umd.min.js \
    && cp node_modules/chart.js/dist/chart.umd.js.map static/vendor/


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

# Startup scripts must be executable regardless of how git checked them out
# (Windows clones lose the exec bit).
RUN chmod +x entrypoint.sh render-start.sh

# Bring in the compiled Tailwind stylesheet + vendored fonts / icons / Chart.js
# from the build stage. Everything here is gitignored, so this is the only path
# by which it reaches the image.
COPY --from=tailwind /build/static/css/output.css static/css/output.css
COPY --from=tailwind /build/static/fonts/ static/fonts/
COPY --from=tailwind /build/static/fontawesome/ static/fontawesome/
COPY --from=tailwind /build/static/vendor/ static/vendor/

EXPOSE 8000

# Default command runs the Django dev server. docker-compose overrides
# this with an entrypoint that waits for the DB and runs migrations first.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
