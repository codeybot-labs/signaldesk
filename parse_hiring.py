"""Parse HN 'Who is hiring?' top-level comments into company/role/location/url/email."""

from __future__ import annotations

import re
from typing import Optional

from textutil import company_domain_from_urls, extract_emails, extract_urls, first_line, strip_html

REMOTE_RE = re.compile(r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.I)
ONSITE_RE = re.compile(r"\b(onsite|on-site|in[- ]office|hybrid)\b", re.I)


def _split_head(line: str) -> list[str]:
    # Company | Role | Location | REMOTE | URL   — also allow en-dash / ' - '
    if "|" in line:
        parts = [p.strip(" -–—") for p in line.split("|")]
    else:
        parts = [p.strip() for p in re.split(r"\s+[–—]\s+", line)]
    return [p for p in parts if p]


def parse_comment(text: str) -> Optional[dict]:
    raw = strip_html(text or "")
    if not raw or len(raw) < 8:
        return None
    head = first_line(raw)
    if not head:
        return None
    # Skip meta comments that aren't job posts
    lower = head.lower()
    if lower.startswith(("note:", "mod:", "please ", "flag ", "edit:")):
        return None

    parts = _split_head(head)
    company = parts[0] if parts else ""
    # If the "company" is a URL, skip
    if company.lower().startswith("http"):
        return None
    # Strip trailing location hints already in the name? keep as-is
    company = re.sub(r"\s*\(.*\)$", "", company).strip() or company
    # "Foo (YC W22)" keep Foo
    company = re.sub(r"\s*\(YC [^)]+\)\s*$", "", company, flags=re.I).strip() or company
    if len(company) < 2 or len(company) > 80:
        return None

    role = parts[1] if len(parts) > 1 else ""
    location = ""
    remote = None
    for part in parts[1:]:
        if REMOTE_RE.search(part) and not re.search(r"^https?://", part, re.I):
            remote = True
            if "hybrid" in part.lower():
                remote = True
        if ONSITE_RE.search(part) and "remote" not in part.lower():
            if remote is None:
                remote = False
        if not re.search(r"^https?://", part, re.I) and part != role:
            if any(ch.isalpha() for ch in part) and ("," in part or REMOTE_RE.search(part) or ONSITE_RE.search(part) or re.search(r"\b(US|UK|EU|CA|NYC|SF|LA|remote)\b", part, re.I)):
                if not location:
                    location = part

    if not location:
        for part in parts[2:]:
            if not re.search(r"^https?://", part, re.I) and not REMOTE_RE.search(part):
                location = part
                break

    if remote is None:
        if REMOTE_RE.search(raw[:800]):
            remote = True
        elif ONSITE_RE.search(raw[:800]):
            remote = False

    urls = extract_urls(raw)
    emails = extract_emails(raw)
    # Prefer contact emails on a company domain later
    domain = company_domain_from_urls(urls)
    contact = ""
    if emails:
        if domain:
            for e in emails:
                if e.lower().endswith("@" + domain) or e.lower().endswith("." + domain):
                    contact = e
                    break
        if not contact:
            contact = emails[0]
        if not domain:
            from textutil import domain_from_email, is_skip_domain
            d = domain_from_email(contact)
            if d and not is_skip_domain(d):
                domain = d

    if not company:
        return None
    quote = head if len(head) <= 280 else head[:277] + "…"
    return {
        "company": company,
        "role": role[:200],
        "location": (location or "")[:200],
        "remote": remote,
        "domain": domain,
        "contact": contact,
        "urls": urls,
        "signal_quote": quote,
        "text": raw[:2000],
    }
