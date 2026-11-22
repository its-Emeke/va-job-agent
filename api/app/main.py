"""FastAPI backend for the VA job agent (web/multi-user, auth-gated)."""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, db, drafts, fetchers, gmail
from .auth import router as auth_router, current_user

app = FastAPI(title="VA Job Agent")

db.init_db()

# CORS only matters for local dev (frontend :5173 → backend :8000). In prod the
# SPA and API share an origin on Vercel. Credentials must be allowed for cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


class DraftEdit(BaseModel):
    subject: str
    body: str


class SearchReq(BaseModel):
    search: str = "virtual assistant"


@app.get("/api/health")
def health():
    """Public liveness check (no auth)."""
    return {"ok": True}


@app.post("/api/fetch")
def fetch(req: SearchReq, user: dict = Depends(current_user)):
    found = fetchers.fetch_all(req.search)
    inserted = sum(1 for j in found if db.upsert_job(j, user["uid"]))
    return {"found": len(found), "new": inserted}


@app.get("/api/jobs")
def jobs(status: str | None = None, user: dict = Depends(current_user)):
    return db.list_jobs(user["uid"], status=status)


@app.get("/api/jobs/{job_id}")
def job(job_id: int, user: dict = Depends(current_user)):
    j = db.get_job(job_id, user["uid"])
    if not j:
        raise HTTPException(404, "job not found")
    return j


@app.post("/api/jobs/{job_id}/draft")
def make_draft(job_id: int, user: dict = Depends(current_user)):
    j = db.get_job(job_id, user["uid"])
    if not j:
        raise HTTPException(404, "job not found")
    subject, body = drafts.generate(j, sender_name=config.MY_NAME, sender_email=user["email"])
    db.save_draft(job_id, user["uid"], subject, body)
    return {"subject": subject, "body": body}


@app.put("/api/jobs/{job_id}/draft")
def edit_draft(job_id: int, edit: DraftEdit, user: dict = Depends(current_user)):
    if not db.get_job(job_id, user["uid"]):
        raise HTTPException(404, "job not found")
    db.save_draft(job_id, user["uid"], edit.subject, edit.body)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/skip")
def skip(job_id: int, user: dict = Depends(current_user)):
    db.set_status(job_id, user["uid"], "skipped")
    return {"ok": True}


@app.post("/api/jobs/{job_id}/gmail-draft")
def to_gmail_draft(job_id: int, user: dict = Depends(current_user)):
    j = _require_sendable(job_id, user["uid"])
    try:
        did = gmail.create_draft(user["uid"], j["contact_email"], j["draft_subject"], j["draft_body"])
    except gmail.GmailNotAuthorized as e:
        raise HTTPException(401, str(e))
    db.set_status(job_id, user["uid"], "approved")
    return {"ok": True, "gmail_draft_id": did}


@app.post("/api/jobs/{job_id}/send")
def send(job_id: int, user: dict = Depends(current_user)):
    j = _require_sendable(job_id, user["uid"])
    if db.sent_today_count(user["uid"]) >= config.DAILY_SEND_LIMIT:
        raise HTTPException(
            429, f"Daily send limit ({config.DAILY_SEND_LIMIT}) reached. "
                 "This cap protects your account from spam flags."
        )
    try:
        mid = gmail.send_message(user["uid"], j["contact_email"], j["draft_subject"], j["draft_body"])
    except gmail.GmailNotAuthorized as e:
        raise HTTPException(401, str(e))
    db.mark_sent(job_id, user["uid"])
    return {"ok": True, "message_id": mid, "sent_today": db.sent_today_count(user["uid"])}


def _require_sendable(job_id: int, user_id: int) -> dict:
    j = db.get_job(job_id, user_id)
    if not j:
        raise HTTPException(404, "job not found")
    if not j.get("contact_email"):
        raise HTTPException(400, "No contact email on this listing — apply via its URL instead.")
    if not j.get("draft_body"):
        raise HTTPException(400, "Generate a draft first.")
    return j
