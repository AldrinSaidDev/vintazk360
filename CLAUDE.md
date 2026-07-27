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
- Brand palette (Tailwind tokens): `ink` #040404, `brand` #4F3D67, `accent` #B27FA0, `blush` #DFADB6, `surface` #202427. Plus **semantic status tokens** `status.good` #4F3D67 (= brand, on-track), `status.warn` #D9A441 (muted amber, at-risk), `status.bad` #C25B6E (muted rose, below). On-track deliberately reuses brand purple so status stays on-brand yet distinguishable.
- **Fonts:** body = **Montserrat**, headings = **Space Grotesk** — both vendored to `static/fonts/` via `@fontsource`, copied by the tailwind container on startup. Tailwind: default `sans` = Montserrat, `font-heading` = Space Grotesk.
- **Charts: Chart.js** (v4, vendored `static/vendor/chart.umd.min.js`, copied by the tailwind container; no CDN). Loaded per-page in `{% block scripts %}`, fed data via `{{ ...|json_script:"id" }}`. Used for the Operations "Actual vs Target" horizontal bar chart (normalized % attainment, direction-aware, colored by status token).
- Base shell `templates/base.html`: dark sidebar with **per-team dropdowns** (see below), top bar (page_title + `dept_badge` block + search + help + avatar dropdown), footer. **No sidebar collapse toggle** (removed).

## Gotchas (learned the hard way)
- Django `{# #}` comments are **single-line only** — multi-line ones render as visible text. (Bit us repeatedly — in the sidebar and the modal. Keep every `{# #}` on one line.)
- Tailwind only compiles classes it finds as **literal strings** while scanning templates. Classes built dynamically in JS (e.g. `'bg-status-' + key`) get purged — reference each full class literally somewhere (it scans inside `<script>` too), or they won't exist in `output.css`.
- Don't put `hidden` and `grid` on the same element (both set `display`) — they conflict. To toggle a grid's visibility from JS, start `hidden` and apply grid via `[&:not(.hidden)]:grid`.
- In arbitrary Tailwind values, `theme(colors.brand-dark)` is invalid (dash) — use `theme(colors.brand.dark)` or a literal hex.
- Renaming/adding apps can wedge the dev-server autoreloader → `docker compose restart web`.
- Login-protected pages can't be screenshotted by headless-Chrome flags (can't POST login) — verify via markup/curl with a session cookie, or Django test client (`Client(SERVER_NAME='localhost')` + `force_login`).
- Adding a class only used in a JS string still needs a CSS rebuild to appear; the tailwind watcher usually catches it, but `docker compose exec tailwind npm run build:css` forces it.

## Auth & access control (BUILT)
- Login-only (no self-registration). Split-screen animated login at `/login/` (North Star theme, sliding overlay). Login field is labelled **Employee ID** (username = employee ID for now, e.g. `2026-01-439`; real API wiring is a later step — a dedicated `employee_id` field + auth backend).
- Test superuser: `admin` / `testpass123` — **test credential, change before real use.** Demo users `demo_<team>` / `demo_manager` / `demo_admin` and `2026-01-439`, all password `demo1234` (throwaway).
- **Role-based access** (`apps/core`): `Team` model (one row per LOB, `slug` = URL namespace) + `UserProfile` (OneToOne, `role` ∈ superadmin/admin/manager/user, M2M `teams`). Rule (`apps/core/access.py`): superadmin/admin (or Django superuser) → all teams; manager → their teams; user → their one team. Everyone sees the shared Dashboard.
- Enforced in TWO places: the sidebar (context processor `apps/core/context_processors.navigation` → `nav_teams`) shows only accessible teams; each LOB view is guarded `@login_required` + `@team_required('<slug>')` (403 otherwise). Profiles auto-created via a `post_save` signal.

## Sidebar navigation (BUILT)
- Each accessible team renders as a **collapsible dropdown** (native `<details>`) of its sub-pages; a team with only one page renders as a plain link. Sub-links are data-driven: the context processor includes a page only if its URL resolves (`<slug>:index` / `:import_data` / `:kpis`), so new per-team pages appear automatically. Operations = Dashboard / Import Data / KPI Definitions; other teams = Dashboard only.

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
- **Operations is the reference implementation.** Its pages (all data-driven from `_OPERATIONS_KPIS` in `apps/operations/views.py`, still static placeholder data): **Dashboard** (`:index`) = summary tiles + Actual-vs-Target bar chart + KPI cards grid; **Import Data** (`:import_data`) = stat cards, KPI Records table, Recent Import History, and an **Add Performance Record modal**; **KPI Definitions** (`:kpis`) = data-driven definition cards (name/category/description/Target/Frequency/"How it's calculated" formula).
- **Add Performance Record modal** (Import Data): pick a KPI → two inputs relabel to that KPI's formula parts (numerator/denominator) → live "How it's calculated" panel computes `num ÷ den × 100`, then direction-aware attainment vs target + status pill. All client-side JS, no persistence yet (Save is a mockup).
- **Attainment math** (shared by dashboard + modal): `up` KPIs = actual/target×100; `down` KPIs (e.g. Attrition threshold) = target/actual×100. Status: ≥100 on-track, 90–99 at-risk, <100 (else) below.
- **Site Lead** now has a data-driven KPI Definitions page (matches Operations' definitions layout; 8 KPIs in `apps/sitelead/views.py`) but no dashboard/import pages yet — still otherwise deferred.

## Current state / directives
- **KPI data is still static placeholder** (user directive — no DB for KPI values yet). All KPI lists/values live in the LOB `views.py` as Python dicts; templates loop over them, so swapping to DB-backed models later means changing only the view's data source. Convert to DB-driven KPI models later.
- **DB models that ARE built:** `core.Team` + `core.UserProfile` (access control) — these are real, migrated, admin-managed. Only KPI *values/definitions* remain static.
- Still NOT built: KPI value models (Team→Metric(weight)→Score, OBActivity, KPI definitions as records); real Excel import; per-team dashboards beyond Operations; the Employee-ID → external-API auth wiring.
- **Ask before committing** — confirm scope with the user.

## Detailed memory
Deeper notes in `~/.claude/projects/c--KHAS-vintazk360/memory/` (LOB architecture, KPI definitions, KPI data model, stack/workflow).
