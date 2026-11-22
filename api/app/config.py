"""Central config from environment / .env.

Works both locally (SQLite + localhost OAuth redirect) and on Vercel
(Postgres via DATABASE_URL + the deployed domain as redirect).
"""
import os
from dotenv import load_dotenv

# Load .env from repo root when present (local dev). On Vercel, env vars are set
# in the dashboard and no .env file exists — load_dotenv is a no-op then.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))


def _get(key: str, default: str = "") -> str:
    return (os.getenv(key) or default).strip()


# --- identity / draft signature ---
MY_NAME = _get("MY_NAME", "Your Name")
MY_HEADLINE = _get("MY_HEADLINE", "Virtual Assistant")
MY_PHONE = _get("MY_PHONE", "")
MY_PORTFOLIO_URL = _get("MY_PORTFOLIO_URL", "")

# --- database ---
# e.g. postgresql+psycopg://user:pass@host/db  (Vercel/Neon). Default: local SQLite.
DATABASE_URL = _get("DATABASE_URL", "")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///" + os.path.join(_ROOT, "jobs.db")

# --- auth / sessions ---
# Random long string; set in Vercel env. Dev fallback is fine for localhost only.
SESSION_SECRET = _get("SESSION_SECRET", "dev-insecure-change-me")
# Comma-separated allowlist of Google emails permitted to use the app.
ALLOWED_EMAILS = [
    e.strip().lower() for e in _get("ALLOWED_EMAILS", "").split(",") if e.strip()
]

# --- Google OAuth (Web client) ---
GOOGLE_CLIENT_ID = _get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = _get("GOOGLE_CLIENT_SECRET", "")
# Public base URL of the deployed app, e.g. https://your-app.vercel.app
# Locally defaults to the dev server origin.
APP_BASE_URL = _get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
OAUTH_REDIRECT_URI = _get("OAUTH_REDIRECT_URI", f"{APP_BASE_URL}/api/auth/callback")

# Where to send the browser after login/logout (the SPA).
FRONTEND_URL = _get("FRONTEND_URL", APP_BASE_URL).rstrip("/")

# --- optional LLM drafts ---
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = _get("ANTHROPIC_MODEL", "claude-opus-4-8")

# --- optional extra job sources ---
ADZUNA_APP_ID = _get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = _get("ADZUNA_APP_KEY", "")
USAJOBS_API_KEY = _get("USAJOBS_API_KEY", "")
USAJOBS_EMAIL = _get("USAJOBS_EMAIL", "")

try:
    DAILY_SEND_LIMIT = int(_get("DAILY_SEND_LIMIT", "15") or "15")
except ValueError:
    DAILY_SEND_LIMIT = 15

# Cookie flags: secure cookies in prod (https), relaxed on localhost.
IS_LOCAL = APP_BASE_URL.startswith("http://localhost") or APP_BASE_URL.startswith("http://127.")
COOKIE_SECURE = not IS_LOCAL
