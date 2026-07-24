# Vintazk360

A Django 6 project. **Development runs on Docker Compose (Postgres); production
runs on Supabase (hosted Postgres).**

| Environment | Database | How |
|-------------|----------|-----|
| **Development** | Local Postgres (Docker container) | `docker compose up` |
| **Production / staging** | Supabase (hosted Postgres) | `DATABASE_URL` → Supabase |

Postgres is used everywhere, so dev matches production.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)

That's it — you do not need Python installed on your host; it runs inside the
container.

---

## Quick start (clone → running)

```bash
git clone <repo-url>
cd vintazk360
cp .env.example .env         # Windows: copy .env.example .env
docker compose up --build
```

Everything (app + Postgres) starts with that one command:

- App: http://localhost:8000
- Admin: http://localhost:8000/admin
- Postgres: `localhost:5432` (user `postgres`, password `postgres`, db `vintazk360`)

Migrations run automatically on startup. To stop:

```bash
docker compose down          # stop containers, keep the database
docker compose down -v       # stop AND delete the database volume (fresh DB)
```

---

## Common commands

### Docker

```bash
docker compose up                 # start (after first build)
docker compose up --build         # rebuild image + start (after dependency changes)
docker compose up -d              # start in the background
docker compose logs -f web        # tail the app logs
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

## Switching to Supabase (production)

The database is chosen entirely by the `DATABASE_URL` environment variable —
no code changes needed.

1. In your Supabase project: **Project Settings → Database → Connection string**
   and copy the connection pooler URL.
2. Set `DATABASE_URL` (and the production `SECRET_KEY` / `ALLOWED_HOSTS`) in your
   host's environment:

   ```
   DATABASE_URL=postgresql://postgres.YOUR_PROJECT_REF:YOUR_PASSWORD@aws-0-YOUR_REGION.pooler.supabase.com:6543/postgres
   DJANGO_SETTINGS_MODULE=config.settings.prod
   SECRET_KEY=your-production-secret
   ALLOWED_HOSTS=your-domain.com
   ```

3. Run migrations against it:

   ```bash
   python manage.py migrate
   ```

SSL is required automatically for any non-local host (see
[`config/settings/base.py`](config/settings/base.py)), so Supabase connections
are encrypted with no extra config.

> **Note:** The Docker `db` service is for local development only. In
> production you point `DATABASE_URL` at Supabase and never run the `db`
> container.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Postgres connection string (Docker Postgres for dev, Supabase for prod). See [`.env.example`](.env.example). |
| `DATABASE_SSL` | No | `require` or `disable` to force SSL on/off. Auto-detected by default (off for `localhost`/`db`, on for remote hosts like Supabase). |
| `DJANGO_SETTINGS_MODULE` | No | `config.settings.dev` (default) or `config.settings.prod`. |
| `SECRET_KEY` | Prod | Required when using `config.settings.prod`. |
| `ALLOWED_HOSTS` | Prod | Comma-separated hostnames; required in production. |

`.env` is gitignored. Never commit real secrets — commit changes to
[`.env.example`](.env.example) instead.

---

## Project layout

```
vintazk360/
├── apps/                    # Django applications
│   └── core/                # Main application (import path: apps.core)
├── config/                  # Django project package
│   ├── settings/            # Split settings
│   │   ├── base.py          # Shared settings
│   │   ├── dev.py           # Development (default)
│   │   └── prod.py          # Production hardening
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── requirements/            # Dependencies split by environment
│   ├── base.txt             # Shared
│   ├── dev.txt              # Development
│   └── prod.txt             # Production
├── static/                  # Project-wide static source files
├── templates/               # Project-wide templates
├── media/                   # User uploads (gitignored)
├── manage.py
├── requirements.txt         # Shim → requirements/dev.txt
├── Dockerfile               # Web app image
├── docker-compose.yml       # Local dev stack (web + Postgres)
├── entrypoint.sh            # Container startup: migrate + runserver
└── .env.example             # Template for your local .env
```

### Settings modules

Settings are split under `config/settings/`. Choose one via the
`DJANGO_SETTINGS_MODULE` environment variable:

- `config.settings.dev` — **default** everywhere (manage.py / wsgi / asgi fall
  back to it), so a fresh clone runs with zero config.
- `config.settings.prod` — production. Requires `SECRET_KEY` and `ALLOWED_HOSTS`
  in the environment and refuses to start without them.
