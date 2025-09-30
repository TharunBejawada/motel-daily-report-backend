# app/utils/gmail_client.py
import os
import time
import base64
import logging
import re
from typing import List, Optional, Dict, Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.utils.whitelist_manager import is_whitelisted

LOGGER = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Conservative retry limits
MSG_RETRIES = 2
ATTACH_RETRIES = 2
MAX_ATTACHMENT_BYTES = 12 * 1024 * 1024  # 12MB cap

# ---------- Auth / Service ----------

def _credentials_path() -> str:
    return os.getenv("GMAIL_TOKEN_PATH", "token.json")

def _client_secret_path() -> str:
    return os.getenv("GMAIL_CLIENT_SECRET_PATH", "credentials.json")

def _build_service(creds: Credentials):
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def get_gmail_service():
    creds = None
    token_file = _credentials_path()
    client_secret = _client_secret_path()

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                LOGGER.warning("Token refresh failed (%s). Removing token.json to re-auth.", e)
                try:
                    os.remove(token_file)
                except Exception:
                    pass
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as token:
            token.write(creds.to_json())

    return _build_service(creds)

# ---------- Gmail helpers ----------

_EMAIL_RE = re.compile(r"<([^>]+)>\s*$")

def _extract_email_address(from_header: str) -> str:
    """
    Extract just the email address for strict whitelist matching.
    """
    if not from_header:
        return ""
    m = _EMAIL_RE.search(from_header)
    if m:
        return m.group(1).strip().lower()
    return from_header.strip().lower()

def _parse_headers(payload_headers: List[Dict[str, str]]) -> Dict[str, str]:
    def first(name: str) -> str:
        return next((h.get("value", "") for h in payload_headers if h.get("name") == name), "")
    return {
        "subject": first("Subject"),
        "from": first("From"),
        "to": first("To"),
        "date": first("Date"),
        "message_id_header": first("Message-ID"),
    }

def _subject_is_daily_report(subject: str) -> bool:
    """
    Flexible subject filter:
    - Matches: 'daily report', 'daily reports', 'daily', 'report'
    - Works even with prefixes like '09.10.25 DAILY REPORT'
    """
    if not subject:
        return False
    subj_lower = subject.lower()
    allowed_keywords = ["daily report", "daily reports", "daily", "report"]
    return any(kw in subj_lower for kw in allowed_keywords)

def _list_message_ids(service, query: Optional[str], max_pages: Optional[int]) -> List[Dict[str, str]]:
    """
    List message IDs with a subject-based query.
    """
    user_id = "me"
    results: List[Dict[str, str]] = []
    page_token = None
    page_count = 0

    # More flexible Gmail query
    base_q = '(subject:daily OR subject:report)'
    q = (f"{base_q} {query}".strip()) if query else base_q

    while True:
        try:
            resp = service.users().messages().list(
                userId=user_id, q=q, pageToken=page_token, maxResults=100
            ).execute()
        except HttpError as e:
            LOGGER.error("[Gmail List] HttpError: %s", e)
            break
        except Exception as e:
            LOGGER.error("[Gmail List] Unknown error: %s", e)
            break

        msgs = resp.get("messages", [])
        results.extend(msgs)
        page_token = resp.get("nextPageToken")
        page_count += 1

        if not page_token or (max_pages and page_count >= max_pages):
            break

    return results

def _get_message_with_retries(service, msg_id: str) -> Optional[Dict[str, Any]]:
    user_id = "me"
    for i in range(MSG_RETRIES):
        try:
            return service.users().messages().get(
                userId=user_id, id=msg_id, format="full"
            ).execute()
        except Exception as e:
            LOGGER.warning("[Gmail Get] Error on %s (attempt %d/%d): %s", msg_id, i+1, MSG_RETRIES, e)
            time.sleep(0.6 * (i + 1))
    return None

def _get_attachment_bytes_with_retries(service, message_id: str, attachment_id: str) -> Optional[bytes]:
    user_id = "me"
    for i in range(ATTACH_RETRIES):
        try:
            att = service.users().messages().attachments().get(
                userId=user_id, messageId=message_id, id=attachment_id
            ).execute()
            data_b64 = att.get("data")
            if not data_b64:
                return None
            raw = base64.urlsafe_b64decode(data_b64.encode("utf-8"))
            if len(raw) > MAX_ATTACHMENT_BYTES:
                LOGGER.warning("Attachment too large (%d) on message %s. Skipping.", len(raw), message_id)
                return None
            return raw
        except Exception as e:
            LOGGER.warning("[Gmail Attachment] Error on %s/%s (attempt %d/%d): %s",
                           message_id, attachment_id, i+1, ATTACH_RETRIES, e)
            time.sleep(0.8 * (i + 1))
    return None

def _walk_parts_for_attachments(service, msg_id: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract PDF/DOCX attachments into memory.
    """
    attachments: List[Dict[str, Any]] = []

    def is_supported(fn: str, mt: str) -> bool:
        fn_l = (fn or "").lower()
        mt_l = (mt or "").lower()
        return fn_l.endswith(".pdf") or "pdf" in mt_l or fn_l.endswith(".docx") or "officedocument.wordprocessingml" in mt_l

    def visit(part: Dict[str, Any]):
        filename = part.get("filename") or ""
        mime_type = part.get("mimeType") or ""
        body = part.get("body", {}) or {}

        if filename and body.get("attachmentId") and is_supported(filename, mime_type):
            raw = _get_attachment_bytes_with_retries(service, msg_id, body["attachmentId"])
            if raw is not None:
                attachments.append({"filename": filename, "mimeType": mime_type, "data": raw})

        for child in (part.get("parts") or []):
            visit(child)

    visit(payload)
    return attachments

def _to_email_dict(msg_data: Dict[str, Any]) -> Dict[str, Any]:
    payload = msg_data.get("payload", {}) or {}
    headers = payload.get("headers", []) or []
    header_map = _parse_headers(headers)

    return {
        "gmail_message_id": msg_data.get("id"),
        "thread_id": msg_data.get("threadId"),
        "internal_date": int(msg_data.get("internalDate", 0)),
        "subject": header_map["subject"] or "",
        "from": header_map["from"] or "",
        "to": header_map["to"] or "",
        "date_header": header_map["date"] or "",
        "message_id_header": header_map["message_id_header"] or "",
        "snippet": msg_data.get("snippet", "") or "",
    }

def _fetch_one_message(service, msg_id: str) -> Optional[Dict[str, Any]]:
    data = _get_message_with_retries(service, msg_id)
    if not data:
        return None

    email = _to_email_dict(data)

    if not _subject_is_daily_report(email["subject"]):
        return None

    sender_email_only = _extract_email_address(email["from"])
    if not is_whitelisted(sender_email_only):
        return None

    attachments = _walk_parts_for_attachments(service, msg_id, data.get("payload", {}) or {})
    print(f"📎 DEBUG: {email['subject']} — Found {len(attachments)} attachments")
    for att in attachments:
        print(f"📁 Attachment: {att['filename']} ({att['mimeType']}) - Size: {len(att['data']) if att.get('data') else 0} bytes")

    email["attachments"] = attachments
    return email


# ---------- Public API ----------

def fetch_recent_emails(limit: int = 5, query: Optional[str] = None) -> List[Dict[str, Any]]:
    service = get_gmail_service()
    ids = _list_message_ids(service, query=query, max_pages=1)
    ids = ids[: max(0, limit)]

    emails: List[Dict[str, Any]] = []
    for m in ids:
        e = _fetch_one_message(service, m["id"])
        if e:
            emails.append(e)
        if len(emails) >= limit:
            break

    id_order = [m["id"] for m in ids]
    emails.sort(key=lambda x: id_order.index(x["gmail_message_id"]) if x["gmail_message_id"] in id_order else 9999)
    print("📧 DEBUG: Total emails fetched from Gmail:", len(emails))
    for e in emails:
        print("📨 SUBJECT:", e["subject"], "FROM:", e["from"])
    return emails

def fetch_all_emails(max_pages: Optional[int] = None, query: Optional[str] = None) -> List[Dict[str, Any]]:
    service = get_gmail_service()
    ids = _list_message_ids(service, query=query, max_pages=max_pages)

    emails: List[Dict[str, Any]] = []
    for m in ids:
        e = _fetch_one_message(service, m["id"])
        if e:
            emails.append(e)

    id_order = [m["id"] for m in ids]
    emails.sort(key=lambda x: id_order.index(x["gmail_message_id"]) if x["gmail_message_id"] in id_order else 9999)
    print("📧 DEBUG: Total emails fetched from Gmail:", len(emails))
    for e in emails:
        print("📨 SUBJECT:", e["subject"], "FROM:", e["from"])

    return emails
