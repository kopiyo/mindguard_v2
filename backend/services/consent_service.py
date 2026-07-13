"""
Consent state machine operations.
Valid transitions:
  DRAFT -> PENDING (dispatch)
  PENDING -> VIEWED (token opened)
  PENDING|VIEWED -> ACCEPTED (accepted)
  PENDING|VIEWED -> DECLINED (declined)
  PENDING|VIEWED -> EXPIRED (TTL elapsed - checked on read)
  ACCEPTED -> REVOKED (revoked)
  ACCEPTED -> RENEWAL_DUE (auto on expiry)
"""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from backend.database import (
    get_consent_by_id,
    update_consent_status,
    write_audit,
)
from backend.services.email_sender import send_html_email

CONSENT_TRANSITIONS = {
    "DRAFT":       ["PENDING"],
    "PENDING":     ["VIEWED", "ACCEPTED", "DECLINED", "EXPIRED"],
    "VIEWED":      ["ACCEPTED", "DECLINED", "EXPIRED"],
    "ACCEPTED":    ["REVOKED", "RENEWAL_DUE"],
    "DECLINED":    ["PENDING"],  # re-dispatch
    "EXPIRED":     ["PENDING"],  # re-dispatch
    "REVOKED":     [],
    "RENEWAL_DUE": ["PENDING"],
}


def _consent_url(token: str) -> str:
    base_url = os.getenv("APP_BASE_URL") or os.getenv("FRONTEND_URL") or "http://localhost:5173"
    return f"{base_url.rstrip('/')}/consent/{token}"


def _send_consent_email(consent: dict, reminder: bool = False) -> tuple[bool, str, str]:
    token = consent.get("magic_token") or ""
    url = _consent_url(token)
    platforms = ", ".join(json.loads(consent.get("platforms_json") or "[]")) or "selected platforms"
    role_label = "parent/guardian" if consent.get("recipient_role") == "parent" else "student"
    subject_prefix = "Reminder: " if reminder else ""
    subject = f"{subject_prefix}MindGuard consent request"
    body_html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;color:#111827;max-width:640px;margin:0 auto;padding:24px;background:#f7f9fb">
  <div style="background:#0F766E;border-radius:10px 10px 0 0;padding:24px 28px">
    <h1 style="color:#ffffff;margin:0;font-size:22px">MindGuard</h1>
    <p style="color:#ccfbf1;margin:6px 0 0;font-size:14px">Consent request for social media wellbeing analysis</p>
  </div>
  <div style="background:#ffffff;border:1px solid #d9e3df;border-top:none;border-radius:0 0 10px 10px;padding:28px">
    <p>Dear {role_label},</p>
    <p>A school counsellor has requested consent to analyse public social media information using MindGuard.</p>
    <p><strong>Requested platforms:</strong> {platforms}</p>
    <p><strong>Consent mode:</strong> {consent.get("mode", "ON_DEMAND").replace("_", " ").title()}</p>
    <p style="margin:24px 0">
      <a href="{url}" style="background:#0F766E;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:8px;font-weight:700;display:inline-block">
        Review consent request
      </a>
    </p>
    <p>If the button does not work, copy and paste this link into your browser:</p>
    <p style="word-break:break-all;color:#0F766E">{url}</p>
    <p style="font-size:13px;color:#64748b">This link expires automatically. You can accept or decline from the consent page.</p>
  </div>
</body>
</html>
"""
    ok, error = send_html_email(consent["recipient_email"], subject, body_html)
    return ok, error, url


def check_and_expire(consent: dict) -> dict:
    """If PENDING/VIEWED and past expires_at, flip to EXPIRED."""
    if consent["status"] not in ("PENDING", "VIEWED"):
        return consent
    expires = consent.get("expires_at")
    if expires and datetime.now(timezone.utc).isoformat() > expires:
        consent = update_consent_status(consent["id"], "EXPIRED") or consent
    return consent


def dispatch_consent(consent_id: str, actor_id: str, ip: str | None = None) -> dict:
    """Transition DRAFT/DECLINED/EXPIRED/RENEWAL_DUE -> PENDING.

    Generates a fresh magic token, refreshes expires_at, and records dispatched_at.
    """
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise ValueError("Consent not found")
    consent = check_and_expire(consent)
    allowed = CONSENT_TRANSITIONS.get(consent["status"], [])
    if "PENDING" not in allowed:
        raise ValueError(f"Cannot dispatch consent in status {consent['status']}")

    now = datetime.now(timezone.utc)
    token = str(uuid.uuid4())
    updated = update_consent_status(
        consent_id,
        "PENDING",
        magic_token=token,
        magic_token_expires_at=(now + timedelta(hours=72)).isoformat(),
        expires_at=(now + timedelta(days=7)).isoformat(),
        dispatched_at=now.isoformat(),
    )
    write_audit(
        actor_id,
        "counsellor",
        "CONSENT_DISPATCHED",
        "consent",
        consent_id,
        payload={"recipient": consent["recipient_email"]},
        ip=ip,
    )
    email_sent, email_error, url = _send_consent_email(updated)
    write_audit(
        actor_id,
        "counsellor",
        "CONSENT_EMAIL_SENT" if email_sent else "CONSENT_EMAIL_FAILED",
        "consent",
        consent_id,
        payload={"recipient": updated["recipient_email"], "error": email_error, "url": url},
        ip=ip,
    )
    updated["email_sent"] = email_sent
    updated["email_error"] = email_error
    updated["consent_url"] = url
    return updated


def remind_consent(consent_id: str, actor_id: str, ip: str | None = None) -> dict:
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise ValueError("Consent not found")
    consent = check_and_expire(consent)
    if consent["status"] not in ("PENDING", "VIEWED"):
        raise ValueError(f"Cannot send reminder for consent in status {consent['status']}")

    email_sent, email_error, url = _send_consent_email(consent, reminder=True)
    write_audit(
        actor_id,
        "counsellor",
        "CONSENT_REMINDER_SENT" if email_sent else "CONSENT_REMINDER_FAILED",
        "consent",
        consent_id,
        payload={"recipient": consent["recipient_email"], "error": email_error, "url": url},
        ip=ip,
    )
    consent["email_sent"] = email_sent
    consent["email_error"] = email_error
    consent["consent_url"] = url
    return consent


def record_view(consent_id: str, ip: str | None = None) -> dict:
    """Record that the consent link was opened (PENDING -> VIEWED)."""
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise ValueError("Consent not found")
    consent = check_and_expire(consent)
    if consent["status"] == "PENDING":
        now = datetime.now(timezone.utc).isoformat()
        consent = update_consent_status(consent_id, "VIEWED", viewed_at=now)
        write_audit(None, "recipient", "CONSENT_VIEWED", "consent", consent_id, ip=ip)
    return consent


def accept_consent(
    consent_id: str,
    signature_name: str,
    ip: str,
    platforms: list | None = None,
) -> dict:
    """Transition PENDING/VIEWED -> ACCEPTED with signature and optional platform list."""
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise ValueError("Consent not found")
    consent = check_and_expire(consent)
    if consent["status"] not in ("PENDING", "VIEWED"):
        raise ValueError(f"Cannot accept consent in status {consent['status']}")

    now = datetime.now(timezone.utc).isoformat()
    final_platforms = platforms if platforms is not None else json.loads(
        consent.get("platforms_json") or "[]"
    )
    updated = update_consent_status(
        consent_id,
        "ACCEPTED",
        signature_name=signature_name,
        signature_ip=ip,
        accepted_at=now,
        platforms_json=json.dumps(final_platforms),
    )
    write_audit(
        None,
        "recipient",
        "CONSENT_ACCEPTED",
        "consent",
        consent_id,
        payload={"signature": signature_name},
        ip=ip,
    )
    return updated


def decline_consent(consent_id: str, ip: str | None = None) -> dict:
    """Transition PENDING/VIEWED -> DECLINED."""
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise ValueError("Consent not found")
    consent = check_and_expire(consent)
    if consent["status"] not in ("PENDING", "VIEWED"):
        raise ValueError(f"Cannot decline consent in status {consent['status']}")

    now = datetime.now(timezone.utc).isoformat()
    updated = update_consent_status(consent_id, "DECLINED", declined_at=now)
    write_audit(None, "recipient", "CONSENT_DECLINED", "consent", consent_id, ip=ip)
    return updated


def revoke_consent(consent_id: str, ip: str | None = None) -> dict:
    """Transition ACCEPTED -> REVOKED."""
    consent = get_consent_by_id(consent_id)
    if not consent:
        raise ValueError("Consent not found")
    if consent["status"] != "ACCEPTED":
        raise ValueError(f"Cannot revoke consent in status {consent['status']}")

    now = datetime.now(timezone.utc).isoformat()
    updated = update_consent_status(consent_id, "REVOKED", revoked_at=now)
    write_audit(None, "recipient", "CONSENT_REVOKED", "consent", consent_id, ip=ip)
    return updated
