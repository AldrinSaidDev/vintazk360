# Vintazk360

A Django 6 project with a Tailwind CSS frontend. **Development runs on Docker
Compose (Postgres); staging runs on Render (web service + Postgres) with
uploaded files in Cloudflare R2.**

| Environment | Database | File storage | How |
|-------------|----------|--------------|-----|
| **Development** | Local Postgres (Docker container) | local disk | `docker compose up` |
| **Staging / production** | Render Postgres | Cloudflare R2 | `DATABASE_URL` + `R2_*` |

Postgres is used everywhere, so dev matches production. Styling is built with
[Tailwind CSS](https://tailwindcss.com/) — see [Styling (Tailwind)](#styling-tailwind).

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)

That's it — you do not need Python **or Node** installed on your host; both run
inside the container (Node compiles the Tailwind CSS).

---

## Quick start (clone → running)

```bash
git clone <repo-url>
cd vintazk360
cp .env.example .env         # Windows: copy .env.example .env
docker compose up --build
```

Everything (app + Postgres + Tailwind watcher) starts with that one command:

- App: http://localhost:8000 (redirects to the login page)
- Admin: http://localhost:8000/admin
- Postgres: `localhost:5432` (user `postgres`, password `postgres`, db `vintazk360`)

The app requires login. Create an account to sign in with:

```bash
docker compose exec web python manage.py createsuperuser
```

Migrations run automatically on startup. To stop:

```bash
docker compose down          # stop containers, keep the database
docker compose down -v       # stop AND delete the database volume (fresh DB)
```

> **Editing code?** You do **not** need to rebuild. Python, templates, and
> Tailwind classes are picked up live — just save and refresh the browser.
> Only rerun `docker compose up --build` when you change dependencies
> (`requirements/*`, `package.json`), the `Dockerfile`, or `docker-compose.yml`.

---

## Common commands

### Docker

```bash
docker compose up                 # start (after first build)
docker compose up --build         # rebuild image + start (after dependency changes)
docker compose up -d              # start in the background
docker compose logs -f web        # tail the app logs
docker compose logs -f tailwind   # tail the Tailwind CSS build/watch
docker compose down               # stop
docker compose down -v            # stop + wipe the dev database

# Run manage.py commands inside the running container:
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py shell

# Open a shell in the container:
docker compose exec web bash

# Connect to the Postgres database:
docker compose exec db psql -U postgres -d vintazk360
```

> All `manage.py` commands run **inside the container** via
> `docker compose exec web ...`. You don't run Python on the host.

---

## Styling (Tailwind)

Styling uses [Tailwind CSS](https://tailwindcss.com/), compiled by a Node
toolchain that also runs in Docker — you do **not** need Node on your host.

- Source: [`static/src/input.css`](static/src/input.css) + the classes you write
  in your templates.
- Config: [`tailwind.config.js`](tailwind.config.js) (scans `templates/` and
  `apps/**/templates/`; defines the `brand` color).
- Output: `static/css/output.css` (a build artifact — **gitignored**, not
  committed), loaded in [`templates/base.html`](templates/base.html).

**In development**, the `tailwind` compose service watches your templates and
rebuilds `output.css` automatically. Add Tailwind classes to any template, save,
and refresh — no rebuild, no manual command. Watch it work with:

```bash
docker compose logs -f tailwind
```

**In production**, the CSS is compiled during the Docker image build (a dedicated
Tailwind build stage), so the running image ships a ready `output.css` with no
Node in the final image.

To build the CSS once manually (rarely needed):

```bash
docker compose run --rm tailwind npm run build:css
```

---

## Staging: Render + Cloudflare R2

Staging is reached over **two independent channels**. Mixing them up is the
usual source of confusion, so they are kept separate:

| Channel | Configured by | Used for |
|---------|---------------|----------|
| **Postgres (Django ORM)** | `DATABASE_URL` → Render Postgres | Models, migrations, the admin — everything Django already does. |
| **Object storage** | `R2_*` → Cloudflare R2 | Uploaded KPI import files, via [`apps/core/storage.py`](apps/core/storage.py). The database stores only a pointer. |

**Development is unaffected by either** — it stays on the Docker Postgres
container with files on local disk.

### 1. Deploy to Render

The repo ships a Blueprint at [`render.yaml`](render.yaml). In the Render
dashboard: **New → Blueprint**, point it at this repo, and it provisions the
Postgres instance and the Docker web service already wired together. It prompts
for the R2 secrets (step 2) and generates `SECRET_KEY` itself.

- `DATABASE_URL` is injected from the provisioned database — never typed by hand.
- `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` are derived from Render's
  `RENDER_EXTERNAL_HOSTNAME` (see [`config/settings/prod.py`](config/settings/prod.py)),
  so the generated `*.onrender.com` URL works with no extra config. Set them
  explicitly only when you attach a custom domain.
- Migrations and `collectstatic` run at container start in
  [`render-start.sh`](render-start.sh), then gunicorn takes over. The Docker
  build cannot run them — it has no `DATABASE_URL`.
- SSL to Postgres is required automatically for any non-local host (see
  [`config/settings/base.py`](config/settings/base.py)).

To connect from your laptop instead (psql, a GUI, a one-off migrate), use the
**External** Database URL from Render → your database → *Connections*; the
internal hostname only resolves inside Render.

### 2. Cloudflare R2

Create a **private** bucket in Cloudflare → R2, then an **Account API token**
with *Object Read & Write* scoped to it (R2 → API → Manage API tokens). That
gives you four values:

```
R2_ACCOUNT_ID=          # R2 Overview → right sidebar → Account ID
R2_ACCESS_KEY_ID=       # from the API token
R2_SECRET_ACCESS_KEY=   # shown ONCE when the token is created
R2_BUCKET=vintazk360-imports
```

Put them in `.env` locally, and in the Render service's **Environment** tab for
staging. The client is built lazily on first use, so unset or unreachable
storage can never stop the app from booting:

```python
from apps.core import storage

storage.upload_fileobj(f, 'operations/2026/08/attrition-<uuid>.csv')
url = storage.signed_url('operations/2026/08/attrition-<uuid>.csv')  # short-lived
```

Check the wiring at any time:

```bash
docker compose exec web python manage.py storage_status          # show config
docker compose exec web python manage.py storage_status --ping   # + reach the bucket
```

> Keep the bucket **private** — no public `r2.dev` URL, no public custom domain.
> Downloads go through a Django view that re-checks team access and returns a
> signed URL; a public bucket would make every team's raw performance data
> readable by anyone with the link.

> **Note:** The Docker `db` service is for local development only. On Render you
> point `DATABASE_URL` at Render Postgres and never run the `db` container.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Postgres connection string (Docker Postgres for dev, Render Postgres for staging). See [`.env.example`](.env.example). |
| `DATABASE_SSL` | No | `require` or `disable` to force SSL on/off. Auto-detected by default (off for `localhost`/`db`, on for remote hosts like Render). |
| `DJANGO_SETTINGS_MODULE` | No | `config.settings.dev` (default), `.staging`, or `.prod`. |
| `SECRET_KEY` | Staging/Prod | Required by `config.settings.staging` and `.prod`. |
| `ALLOWED_HOSTS` | Staging/Prod | Comma-separated hostnames. On Render, `RENDER_EXTERNAL_HOSTNAME` is added automatically. |
| `CSRF_TRUSTED_ORIGINS` | No | Comma-separated origins with scheme. The Render hostname is added automatically. |
| `R2_ACCOUNT_ID` | Staging | Cloudflare account ID — the endpoint is derived from it. |
| `R2_ACCESS_KEY_ID` | Staging | R2 API token key ID. |
| `R2_SECRET_ACCESS_KEY` | Staging | R2 API token secret — server-side only. |
| `R2_BUCKET` | Staging | Bucket name (default `vintazk360-imports`). Must be private. |
| `R2_ENDPOINT_URL` | No | Override only for jurisdiction-specific endpoints. |
| `R2_TIMEOUT` | No | S3 API timeout in seconds (default `10`). |
| `R2_SIGNED_URL_TTL` | No | Download-link lifetime in seconds (default `300`). |
| `WEB_CONCURRENCY` | No | gunicorn worker count on Render (default `2`). |

`.env` is gitignored. Never commit real secrets — commit changes to
[`.env.example`](.env.example) instead.

---

## Project layout

```
vintazk360/
├── apps/                    # Django applications
│   ├── core/                # Base/shared app (import path: apps.core)
│   └── dashboard/           # Dashboard app — home page + templates
├── config/                  # Django project package
│   ├── settings/            # Split settings
│   │   ├── base.py          # Shared settings (incl. database + R2 config)
│   │   ├── dev.py           # Development (default)
│   │   ├── staging.py       # Staging — Render + Cloudflare R2
│   │   └── prod.py          # Production hardening (+ Render/WhiteNoise)
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── requirements/            # Python deps split by environment
│   ├── base.txt             # Shared
│   ├── dev.txt              # Development
│   └── prod.txt             # Production
├── static/
│   ├── src/input.css        # Tailwind entry (source)
│   └── css/output.css       # Compiled Tailwind (build artifact, gitignored)
├── templates/               # Project-wide templates
│   ├── base.html            # Shared shell (Vintazk 360 nav)
│   └── registration/        # Django auth templates (login page)
├── media/                   # User uploads (gitignored)
├── manage.py
├── requirements.txt         # Shim → requirements/dev.txt
├── package.json             # Node/Tailwind build scripts
├── tailwind.config.js       # Tailwind configuration
├── Dockerfile               # Web app image (Tailwind build + Python stages)
├── docker-compose.yml       # Local dev stack (db + web + tailwind)
├── entrypoint.sh            # Dev container startup: migrate + runserver
├── render.yaml              # Render Blueprint (web service + Postgres)
├── render-start.sh          # Render startup: migrate + collectstatic + gunicorn
└── .env.example             # Template for your local .env
```

`node_modules/` (Node deps) and `static/css/output.css` (compiled CSS) are
generated inside Docker and are gitignored — you never commit them.

### Settings modules

Settings are split under `config/settings/`. Choose one via the
`DJANGO_SETTINGS_MODULE` environment variable:

- `config.settings.dev` — **default** everywhere (manage.py / wsgi / asgi fall
  back to it), so a fresh clone runs with zero config.
- `config.settings.staging` — staging on Render. Inherits production's
  hardening (minus sticky HSTS) and additionally refuses to start without the
  Cloudflare R2 credentials.
- `config.settings.prod` — production. Requires `SECRET_KEY` and `ALLOWED_HOSTS`
  in the environment and refuses to start without them.
