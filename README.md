# NS Internal Calendar

A small internal web app where team members log their work hours, classes and
other commitments, see each other's availability, and share events with RSVP.

- **Login by allowlist** - an admin enters members' Microsoft emails; each member
  picks a password on first sign-in. Nobody else can get in.
- **My calendar** - personal entries (work, class, personal, unavailable), one-off
  or repeating (daily / weekly on chosen days, optional end date).
- **Import timetable** - subscribe to an iCal/ICS link (university timetable,
  Outlook/Google "publish" link). Its events show up read-only on your calendar
  and count as busy time for the team, refreshed automatically every 30 minutes.
- **Shared events** - anyone can post an event; members RSVP going / maybe / can't go.
- **Team availability** - everyone's busy blocks overlaid on one week view, plus a
  "find a time when everyone is free" helper.
- **Admin** - add members one by one or in bulk, promote admins, deactivate,
  reset passwords, remove.

Built with **Python + Streamlit**, **PostgreSQL** (SQLAlchemy + psycopg) and
[FullCalendar](https://fullcalendar.io/) via `streamlit-calendar`.

---

## Project layout

```
streamlit_app.py        Entry point: connects to DB, shows login, then the pages
app_pages/
  my_calendar.py        Personal calendar (add / edit / delete entries)
  events.py             Shared events + RSVP
  team.py               Team availability overlay + free-slot finder
  account.py            Change display name / password
  admin.py              Manage members (admins only)
core/
  config.py             Reads settings from secrets / environment
  db.py                 Database engine + session helper + table creation
  models.py             The tables: members, calendar_entries, calendar_feeds, events, rsvps
  auth.py               Password hashing, login, first-time setup
  services.py           All reads/writes the pages use (the "business logic")
  recurrence.py         Expands repeating entries into calendar occurrences
  feeds.py              Downloads and parses iCal/ICS subscription links
certs/                  Extra public CA certificates for feed servers with broken chains
  calendar_ui.py        Draws the FullCalendar widget
  ui.py                 Small shared widgets/helpers
tests/                  pytest suite (runs against a real PostgreSQL)
dev_db/                 Local PostgreSQL for development (no install needed)
.streamlit/
  config.toml           Theme
  secrets.toml.example  Template for your secrets
```

Rule of thumb: pages only call functions in `core/services.py` and `core/auth.py`.
If you need a new feature, add a function there, then use it from a page.

---

## Run locally

Requirements: Python 3.11+, Node.js 18+ (only for the local database).

```bash
# 1. Python environment
python -m venv .venv
.venv\Scripts\activate          # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt

# 2. Local PostgreSQL (real Postgres running via PGlite, data kept in dev_db/data)
cd dev_db && npm install && npm start      # leave this terminal open
cd ..

# 3. Secrets
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
#    -> put YOUR email in admin_emails; keep the local database url

# 4. Start the app
streamlit run streamlit_app.py
```

Open http://localhost:8501, enter your admin email, choose a password, then add
members from **Members (admin)**.

Run the tests (starts its own throwaway in-memory database):

```bash
pytest
```

---

## Deploy for free (Neon + Streamlit Community Cloud)

### 1. Create the PostgreSQL database on Neon

1. Sign up at https://neon.tech (free tier is enough).
2. Create a project. Copy the connection string; it looks like
   `postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`.

Any other PostgreSQL works too (Supabase, Railway, Render, your own server). The
app creates its tables automatically on first start.

### 2. Push the code to GitHub

```bash
git init
git add .
git commit -m "NS internal calendar"
gh repo create ns-internal-calendar --private --source=. --push   # or use the GitHub website
```

`.streamlit/secrets.toml` is git-ignored, so your secrets are never uploaded.

### 3. Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. **New app** -> pick the repo, branch `main`, main file `streamlit_app.py`.
3. Open **Advanced settings -> Secrets** and paste:

   ```toml
   [app]
   org_name = "NS"
   admin_emails = ["you@yourorg.onmicrosoft.com"]

   [database]
   url = "postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require"
   ```

4. Click **Deploy**. You get a public URL like `https://ns-calendar.streamlit.app`.
   Only allowlisted emails can log in, so the URL being public is fine.

Every `git push` redeploys automatically.

### Alternative hosts

The app is a plain Streamlit app, so it also runs on Railway, Render, Fly.io, or
a company server with `streamlit run streamlit_app.py --server.port 80`. Provide
the same values as environment variables instead of secrets:
`DATABASE_URL`, `ADMIN_EMAILS` (comma separated), `ORG_NAME`.

---

## Everyday admin tasks

| Task | Where |
|------|-------|
| Let a new person in | Members (admin) -> Add members (their Microsoft email) |
| Someone forgot their password | Members (admin) -> Reset password; they set a new one at next sign-in |
| Someone left | Members (admin) -> untick **Active** (keeps their history) or **Remove member** |
| Make another admin | Members (admin) -> tick **Admin** -> Save changes |
| Change the org name / bootstrap admins | Edit secrets (`[app]`) and restart |

---

## Importing a university timetable

Most universities provide a personal iCal link ("Add to Outlook on the web /
Google Calendar"). In the app: **My calendar -> Import timetable**, paste the
link, choose a category, **Subscribe**. Imported items are read-only (edit them
at the source); remove the subscription from the same place. The link contains
a personal token, so treat it like a password - the app never shows it to others.

If a feed fails with a certificate error, the server is probably missing its
intermediate certificate; see `certs/README.md`.

## Notes and limits

- Times are stored as naive local time in the organization's timezone
  (`[app].timezone`, default `Europe/London`). Imported feeds are converted to it.
- Sessions live in the browser tab; closing the tab signs you out.
- Passwords are hashed with bcrypt. Only emails and display names are stored.
- Schema changes: `init_db()` creates missing tables but does not alter existing
  ones. If you add a column later, apply it with a small SQL `ALTER TABLE` (or
  adopt Alembic).
