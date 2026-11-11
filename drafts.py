"""Draft-first outreach. Uses ctx.llm.complete when present, else a template."""

from __future__ import annotations

import re
from typing import Any, Optional

from models import ICP, Lead


def _local_draft(lead: Lead, icp: ICP) -> tuple[str, str]:
    prov = lead.provenance or {}
    sender = (icp.sender_name or "there").strip() or "there"
    offer = (icp.local_offer or icp.offer or "a tool that helps local businesses").strip()
    btype = str(prov.get("business_type") or "business").replace("_", " ")
    where = prov.get("address") or lead.location or ""
    seen = f"I came across {lead.company} on OpenStreetMap" + (f" ({where})" if where else "")
    site = (lead.domain or prov.get("website") or "").strip()
    seen += (f" and had a look at {site}." if site else ".")
    web = ""
    booking = f"\nIf useful, grab a time here: {icp.booking_link}\n" if icp.booking_link else ""
    subject = f"Quick idea for {lead.company}"
    body = (
        f"Hi {lead.company} team,\n\n"
        f"{seen}{web}\n\n"
        f"I work on {offer}. If that could help a {btype} like yours, "
        f"I'm happy to send a two-minute walkthrough.\n"
        f"{booking}\n"
        f"Best,\n{sender}\n"
    )
    return subject, body.strip() + "\n"


def template_draft(lead: Lead, icp: ICP) -> tuple[str, str]:
    sender = (icp.sender_name or "there").strip() or "there"
    offer = (icp.offer or "a tool that helps teams like yours").strip()
    signal = (lead.signal_quote or lead.signal_type or "your recent public post").strip()
    if len(signal) > 180:
        signal = signal[:177] + "…"
    role_bit = f" for the {lead.role} role" if lead.role else ""
    if lead.signal_type == "local":
        return _local_draft(lead, icp)
    if lead.signal_type == "hiring":
        opener = (
            f"I saw you're hiring{role_bit}"
            + (f" ({lead.location})" if lead.location else "")
            + "."
        )
        subject = f"Re: {lead.company} hiring" + (f" — {lead.role}" if lead.role else "")
    else:
        opener = f"Congrats on the launch at {lead.company}."
        subject = f"Loved the launch — {lead.company}"

    booking = ""
    if icp.booking_link:
        booking = f"\nIf useful, grab a time here: {icp.booking_link}\n"

    body = (
        f"Hi {lead.company} team,\n\n"
        f"{opener} I noticed: \"{signal}\"\n\n"
        f"I work on {offer}. If that's relevant while you're "
        f"{'hiring' if lead.signal_type == 'hiring' else 'getting this in front of people'}, "
        f"I'm happy to share a short walkthrough.\n"
        f"{booking}\n"
        f"Best,\n{sender}\n"
    )
    return subject.strip(), body.strip() + "\n"


def _extract_subject_body(text: str, fallback_subject: str, fallback_body: str) -> tuple[str, str]:
    text = (text or "").strip()
    if not text:
        return fallback_subject, fallback_body
    # Accept "Subject: ...\n\nBody" or a bare body
    m = re.match(r"(?is)^\s*subject\s*:\s*(.+?)\n\s*\n(.*)$", text)
    if m:
        subject = m.group(1).strip().splitlines()[0][:200]
        body = m.group(2).strip()
        return subject or fallback_subject, (body or fallback_body)
    # First line as subject if short
    lines = text.splitlines()
    if lines and len(lines[0]) <= 90 and not lines[0].lower().startswith("hi "):
        return lines[0].strip(), ("\n".join(lines[1:]).strip() or fallback_body)
    return fallback_subject, text + ("\n" if not text.endswith("\n") else "")


def _llm_complete(llm: Any, prompt: str) -> Optional[str]:
    if llm is None:
        return None
    # Prefer a complete() API; never raise to the tool layer
    for name in ("complete", "generate", "prompt"):
        fn = getattr(llm, name, None)
        if callable(fn):
            try:
                result = fn(prompt)
                if isinstance(result, dict):
                    result = result.get("text") or result.get("content") or result.get("completion")
                return str(result) if result else None
            except TypeError:
                try:
                    result = fn(messages=[{"role": "user", "content": prompt}])
                    if isinstance(result, dict):
                        result = result.get("text") or result.get("content")
                    return str(result) if result else None
                except Exception:
                    continue
            except Exception:
                return None
    return None


def _osm_facts(lead: Lead) -> str:
    prov = lead.provenance or {}
    keys = ("business_type", "address", "website", "phone", "opening_hours")
    return "; ".join(f"{k}={prov[k]}" for k in keys if prov.get(k))


def compose_draft(lead: Lead, icp: ICP, llm: Any = None) -> tuple[str, str, str]:
    """Return (subject, body, method) where method is 'llm' or 'template'."""
    subject, body = template_draft(lead, icp)
    if llm is None:
        return subject, body, "template"
    prompt = (
        "Write a short, specific outreach email (80-130 words) from "
        f"{icp.sender_name or 'the sender'} about: "
        f"{(icp.local_offer if lead.signal_type == 'local' else '') or icp.offer or 'their product'}.\n"
        "Use only facts from the signal below. Do not invent metrics, customers, or titles.\n"
        "Do not include placeholders like [Name] or TBD. No hype.\n"
        f"Company: {lead.company}\n"
        f"Signal type: {lead.signal_type}\n"
        f"Role: {lead.role or 'n/a'}\n"
        f"Location: {lead.location or 'n/a'}\n"
        f"Public signal: {lead.signal_quote}\n"
        + (f"OpenStreetMap details: {_osm_facts(lead)}\n" if lead.signal_type == "local" else "")
        + f"Source: {lead.source_url}\n"
        + (f"Booking link to include: {icp.booking_link}\n" if icp.booking_link else "")
        + "Format exactly:\nSubject: ...\n\n<body>\n"
    )
    text = _llm_complete(llm, prompt)
    if not text:
        return subject, body, "template"
    subject, body = _extract_subject_body(text, subject, body)
    return subject, body, "llm"
