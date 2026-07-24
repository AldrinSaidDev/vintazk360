# Vintazk 360 — Project Guide for Claude

A Django 6 **KPI dashboard** for a BPO/outsourcing org (Nexzys Intelligence / VINTAZK).
This file loads every session — keep it accurate.

## Stack & how to run
- **Dev = Docker only** (Postgres in a container). Prod = Supabase (`DATABASE_URL`). No SQLite.
- Start: `docker compose up --build`. App at http://localhost:8000.
- All Django commands run in the container: `docker compose exec web python manage.py <cmd>`.
- **No rebuild for code/template/CSS changes** — bind mount + auto-reload + tailwind watcher pick them up. Rebuild only for dependency / Dockerfile / compose changes. If the reloader wedges on an app rename, `docker compose restart web`.

## Compose services
- `db` — Postgres. `web` — Django dev server (`config.settings.dev`). `tailwind` — Node container that installs deps, vendors JS/fonts, watches & rebuilds CSS.

## Layout / conventions
- Apps live under `apps/` (import path `apps.<name>`, but each keeps a short `label` so DB tables stay unprefixed).
- Settings split: `config/settings/{base,dev,prod}.py` (dev is default).
- Frontend: **Tailwind** via real Node build (not CDN). Source `static/src/input.css` → `static/css/output.css` (gitignored). Heading font **Space Grotesk** (vendored `static/fonts/`, Tailwind `font-heading`).
- **NO Flowbite** — it was removed (JS didn't init reliably). Don't reintroduce. Interactivity in plain Tailwind: dropdown → `<select>`, avatar menu → native `<details>`, modal → CSS `:target` (`.modal-overlay:target{display:flex}`, open via `href="#id"`, close via `href="#"`).
- **Icons: django-icons + Font Awesome 4** (`{% load icons %}{% icon 'home' %}` → `<i class="fa fa-home">`). FA 4.7 CSS+webfonts vendored to `static/fontawesome/`, loaded in base.html. Use `{% icon %}` for new icons (fa4 names). Existing inline Heroicon SVGs may be migrated over time.
- Brand palette (Tailwind tokens): `ink` #040404, `brand` #4F3D67, `accent` #B27FA0, `blush` #DFADB6, `surface` #202427.
- Base shell `templates/base.html`: collapsible dark sidebar (Dashboard/Import Data/Settings), top bar (page_title + `dept_badge` block + search + help + avatar dropdown), footer ("© Vintazk 360 · Elevating Excellence, Inspiring Innovation · A product of Nexzys Intelligence").

## Gotchas (learned the hard way)
- Django `{# #}` comments are **single-line only** — multi-line ones render as visible text.
- In arbitrary Tailwind values, `theme(colors.brand-dark)` is invalid (dash) — use `theme(colors.brand.dark)` or a literal hex.
- Renaming/adding apps can wedge the dev-server autoreloader → `docker compose restart web`.
- Login-protected pages can't be screenshotted by headless-Chrome flags (can't POST login) — verify via markup/curl with a session cookie.

## Auth
- Login-only (no self-registration). Split-screen animated login at `/login/` (North Star theme, sliding overlay).
- Test superuser: `admin` / `testpass123` (email admin@gmail.com) — **test credential, change before real use.**

## Domain model — LINES OF BUSINESS (LOBs)
Each LOB = its own app under `apps/`, each a login-protected screen:
`sales, hr, academy, operations, finance, sitelead, marketing, nexzys` (+ `dashboard` overview, `core` shared).
Display names: Operations, Site Lead, Sales, HR, VINTAZK Academy, Finance, Social Media (&Marketing), Nexzys.

### Two-dashboard model
- **Overall Dashboard** (`apps/dashboard`) — org-wide rollup, shared to EVERYONE, default landing on login.
- **Per-team/LOB Dashboard** — each LOB has its OWN dashboard = that team's KPI **scorecard** (Actual vs Target + status).

### KPI screens are SCORECARDS, not reference tables
Each KPI has a definition/formula/target/frequency, but the screen's job is to show/enter **actual** performance: **Actual vs Target + status** (on-track/below). Data enters TWO ways: **Excel import** OR **manual entry** (Add Record modal). Mockup ref: Import Data screen = stat cards + KPI Records table + Add Performance Record modal + Recent Import History.

### Operations specifics (current focus)
- Operations oversees MANY teams. **All 7 files in `Excel Files/` are Operations data** — different teams: BPAO, Adparlor, CS Reward (E-commerce), KPI Tracker teams (MediaOps, PubDev, WebDev, JAC, RDAT), ASC, PDDL.
- Two Excel data shapes: (1) **Monthly agent scorecard** (Agent × QA/Attendance/KPI/Behavioral → Performance Rating; metrics/weights vary per team) and (2) **OB call activity log** (ASC/PDDL: agent × date × call outcomes, appointments, revenue).
- The 6 "Operations KPIs" from the North Star image (Attrition, Client Retention, Billable Hours, CSAT, EBR, Seat Expansion) are the leadership ROLLUP.
- **Site Lead is deferred** — focus on Operations only for now.

## Current state / directives
- Building **static mockups, NO DB yet** (user directive). Convert to DB-driven KPI models later.
- Planned models (NOT built): Team (DB records, admin-managed) → Metric(name,weight) → Score; separate OBActivity model; KPI definitions as records.
- Access control planned: Super Admin sees all; other roles a subset; sidebar is per-user. NOT groups-per-LOB. Not built yet.
- **Everything this session is UNCOMMITTED.** Ask before committing; user hasn't committed yet.

## Detailed memory
Deeper notes in `~/.claude/projects/c--KHAS-vintazk360/memory/` (LOB architecture, KPI definitions, KPI data model, stack/workflow).
