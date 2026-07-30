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
- **Logo:** PNG wordmark at `static/img/vintazk-360-logo.png` (committed, not a build artifact). Always render it via `{% include "partials/logo.html" with class="h-8" %}` — never hardcode another `<img>`. The "VINTAZK" text is **white**, so the logo only works on **dark** surfaces (sidebar, login left panel). On light backgrounds use the text lockup instead. Used in: base.html sidebar (all pages), login (both panels), and as the favicon.
- **Fonts:** body = **Montserrat**, headings = **Space Grotesk** — both vendored to `static/fonts/` via `@fontsource`, copied by the tailwind container on startup. Tailwind: default `sans` = Montserrat, `font-heading` = Space Grotesk.
- **Charts: Chart.js** (v4, vendored `static/vendor/chart.umd.min.js`, copied by the tailwind container; no CDN). Loaded per-page in `{% block scripts %}`, fed data via `{{ ...|json_script:"id" }}`. Used for the Operations "Actual vs Target" horizontal bar chart (normalized % attainment, direction-aware, colored by status token).
- Base shell `templates/base.html`: dark sidebar with **per-team dropdowns** (see below), top bar (page_title + `dept_badge` block + search + help + avatar dropdown), footer. **No sidebar collapse toggle** (removed).

## Anti-Slop Design Guidelines
**Every visual element must earn its place.** No gratuitous decoration, animation, or "creative" flourishes for their own sake. The goal is a professional, focused KPI dashboard for business users — not a tech demo.

**Core principle:** Purpose > decoration. Clarity > complexity. Restraint > flashiness.

- **Forms over flash:** Login, inputs, modals, and data-entry UIs must be scannable, fast, and task-focused. No twinkling stars, rotating orbs, glowing blobs, or constellation diagrams. Use spacing and typography to guide the eye, not animations.
- **No "dashboard theater":** Real data, clear charts, and crisp tables beat sci-fi effects. Pulsing nodes, network diagrams, and rotating rings distract from the metrics.
- **Color and gradients: sparingly.** The brand palette (ink, brand, accent, blush, surface, status tokens) is ample. Don't add extra shades, gradients, or shadows unless they create visual hierarchy or affordance.
- **Animation restraint:** Use `transition` for state changes (hover, focus, active). Avoid continuous animations (float, pulse, spin, twinkle, drift) on interactive elements or in the background. If you use animation, keep it under 300ms and tied to user action.
- **The "remove and test" rule:** If you can hide an element and the page still works exactly the same, remove it.
- **Status over style:** When adding a visual effect, ask: "Does this communicate information or improve usability?" If the answer is "it looks cool," it probably stays out.

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
- Each accessible team renders as a **collapsible dropdown** (native `<details>`) of its sub-pages; a team with only one page renders as a plain link. Sub-links are data-driven: the context processor includes a page only if its URL resolves (`<slug>:index` / `:import_data` / `:kpis` / `:kpi_management`), so new per-team pages appear automatically. Operations and Nexzys = Dashboard / Import Data / KPI Definitions / KPI Management; other teams = Dashboard only.
- **Teams can split into branches** (sub-teams) — the dropdown then nests one level deeper. Convention: the LOB app exposes `NAV_BRANCHES = [(slug, name), …]` from `apps/<slug>/branches.py`, and its URLs provide `branch_index` / `branch_import_data` / `branch_kpis` / `branch_kpi_management` taking the branch slug. The context processor discovers this by import — no registry in `core` to keep in sync. A branch team's own `:index` link is relabelled **Overview** so it doesn't read as a sibling of each branch's Dashboard. **Sales is the only branch team** (seo / leadgen / transitions). VCT was briefly modelled this way too — it isn't; see the VCT/SMM/Content note below.

## Domain model — LINES OF BUSINESS (LOBs)
Each LOB = its own app under `apps/`, each a login-protected screen:
`sales, hr, academy, operations, finance, sitelead, vct, smm, content, nexzys` (+ `dashboard` overview, `core` shared).
Display names: Operations, Site Lead, Sales, HR, VINTAZK Academy, Finance, Visual and Content Team, Social Media Management, Content Writing, Nexzys.
**Always spell "Visual and Content Team" out in the UI** — "VCT" is for slugs, app names, and code only (migration `core.0004`).
There is **no `marketing` app** — it was split into `vct` / `smm` / `content` (migration `core.0003`).

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
### Nexzys specifics
- **Nexzys = the internal technology / automation LOB.** Full four-page set built the same way as Operations (data-driven from `_NEXZYS_KPIS` in `apps/nexzys/views.py`, static placeholder values): **Dashboard** (`:index`), **Import Data** (`:import_data`), **KPI Definitions** (`:kpis`, also shows a "Data needed" chip list per KPI), **KPI Management** (`:kpi_management`).
- 8 KPIs: Automation Hours Saved, Automation ROI, System Uptime, IT SLA Compliance, New-Hire Provisioning, Workstation Readiness, AI Copilot Adoption, Security Incidents. Categories: Automation & AI / Infrastructure / Service Delivery / Security.
- **Not every Nexzys KPI is a percentage** — unlike Operations. Each modal KPI declares a `kind` that drives the Add-Record math and wording: `percent` (a÷b×100), `ratio` (a÷b, e.g. "3.4×"), `difference` (a−b hours saved), `days` (two date inputs, ready date − day 0), `count` (single input, major incidents). Security Incidents also carries an optional second pair for training-completion %.
- **Attainment edge cases handled in `apps/nexzys/views.py`:** zero-target KPIs (Security Incidents) are hit/miss, and attainment is bucketed on the *unrounded* value (`_shown()` keeps a 99.96%-vs-99.99% uptime miss from rounding up to "On Track"). Operations' copy of this math still rounds before bucketing.
- **Nexzys has no North Star metric yet** — the dashboard/definitions banner carries a descriptive line instead.

### Sales specifics
- **Sales is the first LOB that splits into branches:** `seo` (SEO & Google Ads), `leadgen` (Lead Generation), `transitions` (Transitions Team). All KPI data lives in `apps/sales/branches.py`; `apps/sales/views.py` holds the math and five views. URLs: `/sales/` (overview) + `/sales/<branch>/{,kpis/,import/,manage/}`.
- **Four templates serve all three branches** (`sales/dashboard|kpi_definitions|import_data|kpi_management.html`), driven by the `branch` context var — adding a fourth branch means one entry in `BRANCHES`, no new templates. `/sales/` renders `overview.html`: one card per branch with its status split and links into its four pages.
- **Sales targets are RANGES, not single numbers** ("40–80/month"). `_attainment()` in `apps/sales/views.py` scores a band: inside the band = 100%; outside it, measured against the edge that was missed, direction-aware. CPL is the one `down` KPI (band ₱750–₱1,500 — a reduction journey, not a ceiling).
- **Some Sales KPIs have no target** (`target_min`/`target_max` = None): the derived rates, plus anything the business hasn't numbered yet. These get a fourth status, `monitored` ("No Target") — neutral slate, no progress bar, excluded from the chart and from the on-track/at-risk/below tallies. Any LOB with derived KPIs will need this.
- Modal `kind`s here: `count` (single tally — most Sales KPIs), `percent`, `cost` (a÷b shown as ₱).
- **Two data judgement calls, both flagged to the user:** "New Logos / Headcount" was split into two KPIs (Lead Gen 9–44 HC, Referral 4–18 HC) because the source row carried two bands; and CTR is `monitored` because the presentation's target is a click volume (500–1,000) while the formula is a percentage.

### Shared KPI page kit (use this for NEW LOBs)
- Operations, Nexzys and Sales each carry their own copy of the math + four templates (built one at a time, before the shape settled). **Everything since — HR, VINTAZK Academy, Finance, VCT, SMM, Content Writing — runs on a shared kit instead**, so a new LOB is a data module + a thin views.py, no new templates.
- `apps/core/kpi.py` — the math (`attainment`/`status`/`shown`/`scorecard`/`counts`) plus one context builder per screen (`dashboard_context`, `definitions_context`, `import_context`, `management_context`). Single targets and Sales-style **range** targets are unified: a single `target` is treated as a band of width zero, so one function serves both. `target=None` → `monitored` ("No Target").
- `templates/kpi/{dashboard,kpi_definitions,import_data,kpi_management,branch_overview}.html` — driven by a `scope` dict `{title, badge, blurb}` plus the context builder's output. `branch_overview` takes branches with pre-resolved URLs so it stays app-agnostic.
- `static/js/kpi-chart.js` + `static/js/kpi-record-modal.js` — the chart and Add-Record calculator, shared. **`./static/js/**/*.js` is in the Tailwind content globs** because the modal script builds status-pill class strings; without it they'd be purged. Vendored libs are deliberately NOT scanned.
- Modal `kind`s the shared script understands: `percent` (a÷b×100), `count` (single tally, second field hidden), `average` (a÷b + unit suffix — days, ratings), `ratio` ("3.4×"), `cost` (₱), `difference` (a−b), `days` (two date inputs), `net_percent` ((a−b)÷a×100 — accuracy net of errors), `variance` ((a−b)÷b×100, signed display but graded on |value|), `accuracy` ((1−|a−b|÷b)×100), `scaled` ((a÷b)×c — the only kind with a **third** input, added for DSO).
- `evaluate()` in the modal script may return a `score` separate from `value`, for KPIs where the number shown isn't the number graded (a −3.2% budget variance shows signed, grades as 3.2 against a ±5 tolerance). `apps/core/kpi.py` does the same server-side by storing the magnitude in `actual` and the signed string in `actual_display`.
- **Two-sided tolerances** ("within ±5%") are modelled as a `down` KPI over a `target_min=0 / target_max=5` band on the absolute value — so overspend and underspend are both penalised past the tolerance, and anything inside it is 100%. Verified: 0/3.2/5 → 100%, 6.5 → 76.9%, 12 → 41.7%.
- Migrating Operations/Nexzys/Sales onto this kit is still outstanding — they work, so they were left alone.

### HR / Academy specifics
- **HR** (`apps/hr/kpis.py`, 9 KPIs) and **VINTAZK Academy** (`apps/academy/kpis.py`, 7 KPIs) are flat LOBs on the shared kit. Both use the `average` kind for day-count KPIs (time-to-fill, speed-to-proficiency) and Academy uses it for the 5-point satisfaction rating; HR's eNPS is a `difference` (% promoters − % detractors).

### VCT / SMM / Content Writing — three separate departments
- **VCT *is* the Visual and Content Team.** SMM and Content Writing are their own departments, NOT branches under it. They were first built as three branches of a single `marketing` LOB; that was wrong and has been undone — don't reintroduce it.
- Three flat apps on the shared kit: `apps/vct` (5 KPIs, `/vct/`), `apps/smm` (3 KPIs, `/smm/`), `apps/content` (5 KPIs, `/content/`). The old `apps/marketing` is deleted and `/marketing/` now 404s.
- Migration `core.0003_split_marketing_into_departments` **repurposes the old `marketing` Team row as `vct`** (keeping its PK so user assignments survive) and adds `smm` + `content`. Team slugs must match the URL namespace — the sidebar and `team_required` both key off them, so a new department needs a Team row or every user gets a 403.
- **Three source mismatches flagged, not silently resolved:** SMM's "Social Media Client Lead Contribution" is `monitored` (target is a lead count, formula is a percentage); Content's "Link Click Performance" is `monitored` (target is "meet/exceed campaign target"); and Content Engagement Rate's target says "of followers" while the formula divides by reach (scored against reach, noted in its description).
### Finance specifics
- `apps/finance/kpis.py`, 9 KPIs on the shared kit. Categories: Payroll / Receivables / Payables / Controls / Planning.
- Finance is what forced the four extra modal kinds: `net_percent` (payroll + invoice accuracy), `scaled` (DSO's three inputs), `variance` (budget variance), `accuracy` (cash-flow forecast).

- **Site Lead** now has a data-driven KPI Definitions page (matches Operations' definitions layout; 8 KPIs in `apps/sitelead/views.py`) but no dashboard/import pages yet — still otherwise deferred.

## Current state / directives
- **KPI data is still static placeholder** (user directive — no DB for KPI values yet). All KPI lists/values live in the LOB `views.py` as Python dicts; templates loop over them, so swapping to DB-backed models later means changing only the view's data source. Convert to DB-driven KPI models later.
- **DB models that ARE built:** `core.Team` + `core.UserProfile` (access control) — these are real, migrated, admin-managed. Only KPI *values/definitions* remain static.
- Still NOT built: KPI value models (Team→Metric(weight)→Score, OBActivity, KPI definitions as records); real Excel import; Site Lead's dashboard/import/management screens (it has KPI Definitions only — every other LOB now has all four); the Employee-ID → external-API auth wiring.
- **Ask before committing** — confirm scope with the user.

## Detailed memory
Deeper notes in `~/.claude/projects/c--KHAS-vintazk360/memory/` (LOB architecture, KPI definitions, KPI data model, stack/workflow).
