import os
import re
import smtplib
import ssl
from email.message import EmailMessage


# ------------------------------------------------------------------
# PII REDACTION
# ------------------------------------------------------------------
# Strips anything that looks like a secret or account identifier before
# an escalation summary is ever stored or emailed.

_PATTERNS = [
    (re.compile(r"\b(?:otp|pin|password|passcode)\b\s*(?:is|:|=|-)?\s*\d{3,8}\b", re.I), "[REDACTED]"),
    (re.compile(r"\b\d{3,8}\b(?=[^.]{0,20}\b(?:otp|pin|code|password)\b)", re.I), "[REDACTED]"),
    (re.compile(r"\b\d{9,18}\b"), "[REDACTED-NUMBER]"),          # account / govt ID length numbers
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[REDACTED-CARD]"),  # card-like grouped digits
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED-EMAIL]"),
]


def redact_pii(text: str) -> str:
    if not text:
        return text
    cleaned = text
    for pattern, repl in _PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    return cleaned


# ------------------------------------------------------------------
# EMAIL NOTIFICATION
# ------------------------------------------------------------------
# Reads SMTP config from env vars. If not configured, dry-runs (prints
# instead of failing) so the agent still works end-to-end while testing.

SMTP_HOST = os.getenv("ESCALATION_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("ESCALATION_SMTP_PORT", "587"))
SMTP_USER = os.getenv("ESCALATION_SMTP_USER", "")
SMTP_PASS = os.getenv("ESCALATION_SMTP_PASS", "")
TO_ADDRESS = os.getenv("ESCALATION_TO_EMAIL", "teacher-oncall@example.org")
FROM_ADDRESS = os.getenv("ESCALATION_FROM_EMAIL", SMTP_USER or "alexa-agent@example.org")


def send_escalation_email(subject: str, body: str) -> bool:
    """Returns True if actually sent, False if it ran in dry-run mode."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        print("=== [DRY RUN] escalation email not sent (no SMTP configured) ===")
        print(f"To: {TO_ADDRESS}\nSubject: {subject}\n\n{body}")
        print("=== end dry run ===")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = FROM_ADDRESS
    msg["To"] = TO_ADDRESS
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
    return True


def format_escalation_summary(record: dict) -> str:
    return (
        f"Reference: {record['reference_id']}\n"
        f"Who: {record['user_id']}\n"
        f"Reason: {record['reason_code']}\n"
        f"Urgency: {record['urgency'].upper()}\n"
        f"What happened: {record['what_happened']}\n"
        f"What the agent already checked: {record['what_agent_checked']}\n"
        f"Language: {record['language']}\n"
        f"Preferred follow-up: {record['follow_up_method']}\n"
        f"Created: {record['created_at']}\n"
    )