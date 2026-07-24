# Vintazk360

A Django 6 project with a Tailwind CSS frontend. **Development runs on Docker
Compose (Postgres); production runs on Supabase (hosted Postgres).**

| Environment | Database | How |
|-------------|----------|-----|
| **Development** | Local Postgres (Docker container) | `docker compose up` |
| **Production / staging** | Supabase (hosted Postgres) | `DATABASE_URL` → Supabase |

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
│   ├── core/                # Base/shared app (import path: apps.core)
│   └── dashboard/           # Dashboard app — home page + templates
├── config/                  # Django project package
│   ├── settings/            # Split settings
│   │   ├── base.py          # Shared settings
│   │   ├── dev.py           # Development (default)
│   │   └── prod.py          # Production hardening
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
├── entrypoint.sh            # Container startup: migrate + runserver
└── .env.example             # Template for your local .env
```

`node_modules/` (Node deps) and `static/css/output.css` (compiled CSS) are
generated inside Docker and are gitignored — you never commit them.

### Settings modules

Settings are split under `config/settings/`. Choose one via the
`DJANGO_SETTINGS_MODULE` environment variable:

- `config.settings.dev` — **default** everywhere (manage.py / wsgi / asgi fall
  back to it), so a fresh clone runs with zero config.
- `config.settings.prod` — production. Requires `SECRET_KEY` and `ALLOWED_HOSTS`
  in the environment and refuses to start without them.
