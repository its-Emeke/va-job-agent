"""Gmail send/draft using credentials stored per-user in the DB.

The OAuth consent happens at login (see auth.py); here we just rebuild the
Credentials object from the stored JSON, refresh it if needed, and call the API.
"""
import base64
import json
from email.mime.text import MIMEText

from . import config, db


class GmailNotAuthorized(Exception):
    pass


def _service(user_id: int):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    raw = db.get_gmail_token(user_id)
    if not raw:
        raise GmailNotAuthorized("No Gmail authorization on file — sign in again.")

    data = json.loads(raw)
    creds = Credentials.from_authorized_user_info(data)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            db.save_gmail_token(user_id, creds.to_json())
        else:
            raise GmailNotAuthorized("Gmail session expired — sign in again.")
    return build("gmail", "v1", credentials=creds)


def _raw_message(to: str, subject: str, body: str) -> dict:
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def create_draft(user_id: int, to: str, subject: str, body: str) -> str:
    svc = _service(user_id)
    draft = svc.users().drafts().create(
        userId="me", body={"message": _raw_message(to, subject, body)}
    ).execute()
    return draft.get("id", "")


def send_message(user_id: int, to: str, subject: str, body: str) -> str:
    svc = _service(user_id)
    sent = svc.users().messages().send(
        userId="me", body=_raw_message(to, subject, body)
    ).execute()
    return sent.get("id", "")
