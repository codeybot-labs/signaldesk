"""Parse HN 'Who is hiring?' top-level comments into company/role/location/url/email."""

from __future__ import annotations

import re
from typing import Optional

from textutil import company_domain_from_urls, extract_emails, extract_urls, first_line, strip_html

REMOTE_RE = re.compile(r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.I)
ONSITE_RE = re.compile(r"\b(onsite|on-site|in[- ]office|hybrid)\b", re.I)
URL_RE = re.compile(r"https?://\S+", re.I)
# Pipe segments that are logistics, not a job title.
META_PART_RE = re.compile(
    r"^(?:"
    r"remote(?:\b.*)?|onsite(?:\b.*)?|on-site(?:\b.*)?|hybrid(?:\b.*)?|"
    r"full[- ]?time.*|part[- ]?time.*|contract.*|hourly.*|internship.*|"
    r"visa\b.*|relocation.*|no visa.*|"
    r"[\d$€£¥].*|"  # compensation
    r".*\b(US|UK|EU|EER|USA|Canada|NYC|SF|LA)\b.*"
    r")$",
    re.I,
)
LOCATIONISH_RE = re.compile(
    r"(,)|(\b(remote|onsite|on-site|hybrid|US|UK|EU|CA|NYC|SF|LA|worldwide)\b)|"
    r"(\b(New York|San Francisco|London|Berlin|Austin|Paris|Toronto|Seattle|Boston)\b)",
    re.I,
)


def _split_head(line: str) -> list[str]:
    # Company | Role | Location | REMOTE | URL   — also allow en-dash / ' - '
    if "|" in line:
        parts = [p.strip(" -–—") for p in line.split("|")]
    else:
        parts = [p.strip() for p in re.split(r"\s+[–—]\s+", line)]
    return [p for p in parts if p]


def _clean_head(line: str) -> str:
    """Header only: drop trailing URLs and collapse whitespace."""
    line = URL_RE.sub("", line or "")
    line = re.sub(r"\(\s*\)", "", line)
    line = re.sub(r"\(\s*(?=\|)", "", line)
    line = re.sub(r"\(\s*$", "", line)
    line = re.sub(r"\s{2,}", " ", line)
    line = re.sub(r"\s+\|\s*$", "", line).strip(" |-–—")
    return line


def parse_comment(text: str) -> Optional[dict]:
    raw = strip_html(text or "")
    if not raw or len(raw) < 8:
        return None
    head = _clean_head(first_line(raw))
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
    # "Foo (YC W22)" or "Foo (Series B)" → Foo when the paren is a trailing tag
    company = re.sub(r"\s*\(YC [^)]+\)\s*$", "", company, flags=re.I).strip() or company
    company = re.sub(r"\s*\((?:Series [A-F]|stealth|seed|early stage)[^)]*\)\s*$", "", company, flags=re.I).strip() or company
    company = company.strip(" (")
    # "Cologne, Germany | UMH | Product Engineer" — first pipe is a place, not a firm
    if re.match(r"^[A-Z][A-Za-z .\-]+,\s*[A-Z]", company) and len(parts) >= 3:
        maybe = parts[1]
        if maybe and not META_PART_RE.match(maybe) and not LOCATIONISH_RE.search(maybe) and not re.search(r"^https?://", maybe, re.I):
            company = maybe
            parts = [company] + parts[2:]
    if len(company) < 2 or len(company) > 80:
        return None

    role = ""
    for part in parts[1:]:
        if re.search(r"^https?://", part, re.I):
            continue
        if META_PART_RE.match(part) or LOCATIONISH_RE.search(part) and len(part) <= 80:
            # logistics / location — not a title
            continue
        if REMOTE_RE.search(part) or ONSITE_RE.search(part):
            continue
        role = part
        break

    def _is_bare_workmode(part: str) -> bool:
        return bool(re.match(r"^(remote|onsite|on-site|hybrid)(\b.*)?$", part.strip(), re.I)) and "," not in part and len(part) < 28

    location = ""
    remote = None
    location_candidates = []
    for part in parts[1:]:
        if re.search(r"^https?://", part, re.I):
            continue
        if REMOTE_RE.search(part):
            remote = True
        if ONSITE_RE.search(part) and "remote" not in part.lower():
            if remote is None:
                remote = False
        if part != role and LOCATIONISH_RE.search(part) and len(part) <= 80:
            location_candidates.append(part)

    # Prefer a geographic fragment over a bare REMOTE/ONSITE/HYBRID tag.
    for part in location_candidates:
        if not _is_bare_workmode(part):
            location = part
            break
    if not location and location_candidates:
        location = location_candidates[0]

    if not location:
        for part in parts[2:]:
            if re.search(r"^https?://", part, re.I):
                continue
            if part == role or _is_bare_workmode(part):
                continue
            if META_PART_RE.match(part) and not LOCATIONISH_RE.search(part):
                continue
            if len(part) <= 80:
                location = part
                break

    if remote is None:
        if REMOTE_RE.search(raw[:800]):
            remote = True
        elif ONSITE_RE.search(raw[:800]):
            remote = False

    urls = extract_urls(raw)
    emails = extract_emails(raw)
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
    quote = head if len(head) <= 160 else head[:157] + "…"
    return {
        "company": company,
        "role": (role or "")[:200],
        "location": (location or "")[:200],
        "remote": remote,
        "domain": domain,
        "contact": contact,
        "urls": urls,
        "signal_quote": quote,
        "text": raw[:2000],
    }
