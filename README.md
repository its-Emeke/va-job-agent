# VA Job Agent

Finds **US-based remote virtual-assistant** jobs from public job-board APIs and
helps you apply by drafting a tailored email per listing that **you review and
approve** before anything is sent. Deployable to **Vercel** with **Google
sign-in** (which also authorizes Gmail sending).

> **Design choice: human-in-the-loop, not a spam bot.**
> The agent *drafts*; you approve. A low daily send cap is enforced. This keeps
> you compliant with the US CAN-SPAM Act and Gmail's sending policy, and tailored
> low-volume outreach actually gets replies — blasting cold emails gets your
> account flagged.

## Architecture

- **Frontend:** React + Vite (static) — login gate + dashboard.
- **Backend:** FastAPI as a Vercel Python serverless function (`api/index.py`).
- **Database:** Postgres in production (via `DATABASE_URL`), SQLite locally.
- **Auth:** "Sign in with Google" → one consent logs you in *and* grants Gmail
  send/compose. Sessions are JWT cookies. Access limited to `ALLOWED_EMAILS`.
- **Gmail tokens** are stored per-user in the DB (serverless has no persistent disk).

```
api/
  index.py            # Vercel entry — exposes the FastAPI `app`
  app/                # config, db (SQLAlchemy), auth, gmail, fetchers, filters, drafts, main
frontend/             # Vite SPA
vercel.json           # build + routing
requirements.txt      # Python deps (root, for the function)
```

---

## Run locally

**Backend** (from `api/`):
```powershell
cd api
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r ..\requirements.txt
# copy ..\.env.example to ..\.env and fill it in (SQLite is the default DB)
uvicorn app.main:app --reload --port 8000
```

**Frontend** (from `frontend/`):
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. To test **login locally**, you still need a Google
Web OAuth client (below) with `http://localhost:8000/api/auth/callback` added as a
redirect URI, and `GOOGLE_CLIENT_ID/SECRET` set in `.env`.

---

## Deploy to Vercel

### 1. Create a Postgres database (Neon — free)
1. Sign up at [neon.tech](https://neon.tech/) → create a project.
2. Copy the connection string. **Convert the prefix** for SQLAlchemy + psycopg:
   - Neon gives: `postgresql://user:pass@host/db?sslmode=require`
   - Use: `postgresql+psycopg://user:pass@host/db?sslmode=require`
   This is your `DATABASE_URL`.

### 2. Create a Google **Web** OAuth client
*(This is a new client — the earlier Desktop one won't work for a web redirect.)*
1. [Google Cloud Console](https://console.cloud.google.com/) → your project.
2. **APIs & Services → Library** → enable **Gmail API** (if not already).
3. **OAuth consent screen → Audience** → keep **Testing**, and add your Gmail
   under **Test users**.
4. **Credentials → Create Credentials → OAuth client ID → Web application**.
   - **Authorized redirect URIs:** add (you'll add the real domain after first deploy)
     - `http://localhost:8000/api/auth/callback` (for local testing)
   - Create → copy the **Client ID** and **Client secret**.

### 3. Push to GitHub, then import to Vercel
1. `git init && git add . && git commit -m "VA job agent"` → push to a GitHub repo.
2. [vercel.com](https://vercel.com/) → **Add New → Project** → import the repo.
   Vercel reads `vercel.json` (builds the Vite app, deploys the Python function).

### 4. Set environment variables in Vercel
Project → **Settings → Environment Variables**:

| Variable | Value |
|---|---|
| `DATABASE_URL` | your `postgresql+psycopg://…` string |
| `SESSION_SECRET` | long random string (`python -c "import secrets;print(secrets.token_urlsafe(48))"`) |
| `GOOGLE_CLIENT_ID` | from step 2 |
| `GOOGLE_CLIENT_SECRET` | from step 2 |
| `ALLOWED_EMAILS` | your Gmail (comma-separate for more) |
| `APP_BASE_URL` | your Vercel URL, e.g. `https://your-app.vercel.app` |
| `FRONTEND_URL` | same as `APP_BASE_URL` |
| `MY_NAME`, `MY_HEADLINE`, … | optional signature / job-source keys |

Deploy.

### 5. Wire the real domain into Google, then redeploy
1. After the first deploy you'll have `https://your-app.vercel.app`.
2. In the Google Web OAuth client, **add** `https://your-app.vercel.app/api/auth/callback`
   to Authorized redirect URIs.
3. Make sure `APP_BASE_URL` / `FRONTEND_URL` in Vercel match that domain → redeploy.

Visit the site → **Sign in with Google** → you're in.

---

## Notes & caveats

- **Google "Testing" mode:** tokens expire after 7 days while the consent screen is
  unpublished. For personal use that just means re-signing-in occasionally.
- **Lock it down:** always set `ALLOWED_EMAILS` before the site is public — otherwise
  anyone with a Google account could sign in (and send from *their own* Gmail, but
  still use your deployment and database).
- **Most listings have no public email** and route to an application form; the email
  agent only fires on the subset that publish an address.
- **Sources:** Remotive + Jobicy are always on; Adzuna + USAJOBS activate when you
  add their free keys. See `.env.example`.
- This tool uses only public APIs and each user's own Gmail. It does not scrape
  sites that forbid it, and it does not mass-send.
