"""Fail-closed send guard. Unattended cron can never send outreach."""

from __future__ import annotations

import re
from typing import Any, Optional

from models import SENDABLE_STAGES
from store import find_by_contact, find_by_domain, get_lead
from textutil import domain_from_email, extract_emails

# Names that look like they would actually transmit a message.
_SEND_NAME = re.compile(
    r"(send_email|email_send|send_mail|mail_send|gmail_send|smtp|"
    r"send_message|send_outreach|dispatch_email|ses_send|mailgun|"
    r"postmark|sendgrid|resend)",
    re.I,
)

# Our own prepare_send writes a local .eml / mailto — it does not transmit.
_SAFE_OWN = {"signaldesk_prepare_send", "signaldesk_draft", "signaldesk_approve", "signaldesk_mark"}


def _looks_like_send(tool_name: str) -> bool:
    name = tool_name or ""
    if name in _SAFE_OWN:
        return False
    if name.startswith("signaldesk_"):
        return "send" in name and "prepare" not in name
    return bool(_SEND_NAME.search(name))


def _recipient_from_args(args: Optional[dict]) -> str:
    if not args:
        return ""
    for key in ("to", "recipient", "email", "address", "mail_to", "recipient_email"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list) and val:
            return str(val[0]).strip()
    # Sometimes a body/mailto
    for key in ("mailto", "message", "body"):
        val = args.get(key)
        if isinstance(val, str):
            found = extract_emails(val)
            if found:
                return found[0]
    return ""


def _approved_lead_for(recipient: str, lead_id: str = "") -> bool:
    if lead_id:
        lead = get_lead(lead_id)
        if lead and lead.stage in SENDABLE_STAGES:
            return True
    if not recipient:
        return False
    emails = extract_emails(recipient) or ([recipient] if "@" in recipient else [])
    for email in emails:
        lead = find_by_contact(email)
        if lead and lead.stage in SENDABLE_STAGES:
            return True
        domain = domain_from_email(email)
        if domain:
            lead = find_by_domain(domain)
            if lead and lead.stage in SENDABLE_STAGES:
                return True
    return False


def make_pre_tool_call(ctx: Any):
    """Build a pre_tool_call hook closed over PluginContext."""

    def pre_tool_call(tool_name: str, args: dict, task_id: str = "", **kwargs) -> Optional[dict]:
        try:
            if not _looks_like_send(tool_name):
                return None
            # Fail closed: any scheduled / unattended cron run may not send.
            cron = None
            try:
                cron = ctx.current_cron_execution() if ctx is not None else None
            except Exception:
                cron = None
            if cron is not None:
                return {
                    "action": "block",
                    "message": (
                        "SignalDesk blocked a send during a cron/unattended run. "
                        "Outreach is draft-first and must be approved and sent in an interactive session."
                    ),
                }
            args = args or {}
            recipient = _recipient_from_args(args)
            lead_id = str(args.get("lead_id") or args.get("id") or "")
            if _approved_lead_for(recipient, lead_id):
                return None
            return {
                "action": "block",
                "message": (
                    "SignalDesk blocked a send: no approved lead matches this recipient. "
                    "Draft with signaldesk_draft, then signaldesk_approve, and only then send."
                ),
            }
        except Exception:
            # Fail closed on hook errors for send-like tools.
            return {
                "action": "block",
                "message": "SignalDesk send guard failed closed. No message was sent.",
            }

    return pre_tool_call
