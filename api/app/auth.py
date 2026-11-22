"""Google OAuth login (doubles as Gmail authorization) + JWT session cookies.

One consent grants sign-in (openid/email/profile) AND Gmail send/compose, so
logging in also authorizes the email agent. Access is restricted to the emails
in ALLOWED_EMAILS. Sessions are stateless JWT cookies (serverless-friendly).
"""
import os
import time
import json

import httpx
import jwt
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse

from . import config, db

# Google often returns a superset of requested scopes (adds openid); relax the
# strict scope-equality check in oauthlib so fetch_token doesn't raise.
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]

SESSION_COOKIE = "session"
STATE_COOKIE = "oauth_state"
SESSION_TTL = 7 * 24 * 3600  # 7 days

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_config() -> dict:
    return {
        "web": {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [config.OAUTH_REDIRECT_URI],
        }
    }


def _flow(state: str | None = None):
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = config.OAUTH_REDIRECT_URI
    return flow


def _make_session(uid: int, email: str) -> str:
    payload = {"uid": uid, "email": email, "exp": int(time.time()) + SESSION_TTL}
    return jwt.encode(payload, config.SESSION_SECRET, algorithm="HS256")


def _read_session(token: str) -> dict | None:
    try:
        return jwt.decode(token, config.SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def current_user(request: Request) -> dict:
    """FastAPI dependency: require a valid session; returns {uid, email}."""
    token = request.cookies.get(SESSION_COOKIE)
    data = _read_session(token) if token else None
    if not data:
        raise HTTPException(401, "Not authenticated")
    return {"uid": data["uid"], "email": data["email"]}


@router.get("/login")
def login():
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        raise HTTPException(500, "Google OAuth not configured (set GOOGLE_CLIENT_ID/SECRET).")
    flow = _flow()
    url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    resp = RedirectResponse(url)
    resp.set_cookie(
        STATE_COOKIE, state, max_age=600, httponly=True,
        secure=config.COOKIE_SECURE, samesite="lax",
    )
    return resp


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None):
    saved_state = request.cookies.get(STATE_COOKIE)
    if not code or not state or state != saved_state:
        raise HTTPException(400, "Invalid OAuth state or missing code.")

    flow = _flow(state=state)
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Fetch the user's email/name from Google.
    info = httpx.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=15,
    ).json()
    email = (info.get("email") or "").lower()
    name = info.get("name")

    if not email:
        raise HTTPException(400, "Could not read email from Google.")
    if config.ALLOWED_EMAILS and email not in config.ALLOWED_EMAILS:
        raise HTTPException(403, f"{email} is not authorized to use this app.")

    user = db.get_or_create_user(email, name)
    # Persist Gmail credentials so the serverless function can send later.
    db.save_gmail_token(user["id"], creds.to_json())

    resp = RedirectResponse(config.FRONTEND_URL or "/")
    resp.set_cookie(
        SESSION_COOKIE, _make_session(user["id"], email), max_age=SESSION_TTL,
        httponly=True, secure=config.COOKIE_SECURE, samesite="lax",
    )
    resp.delete_cookie(STATE_COOKIE)
    return resp


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return {
        "email": user["email"],
        "llm": bool(config.ANTHROPIC_API_KEY),
        "daily_limit": config.DAILY_SEND_LIMIT,
        "sent_today": db.sent_today_count(user["uid"]),
    }


@router.post("/logout")
def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE)
    return resp
