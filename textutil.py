"""HTML stripping, URL/email/domain helpers. No secrets, no shell."""

from __future__ import annotations

import re
from html import unescape
from typing import Optional
from urllib.parse import urlparse

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
# Skip these as company domains (job boards, social, the discussion site)
SKIP_DOMAINS = frozenset({
    "news.ycombinator.com", "hn.algolia.com", "ycombinator.com", "www.ycombinator.com",
    "github.com", "gitlab.com", "linkedin.com", "www.linkedin.com", "twitter.com", "x.com",
    "docs.google.com", "google.com", "forms.gle", "bit.ly", "youtu.be", "youtube.com",
    "notion.so", "notion.site", "medium.com", "substack.com", "reddit.com", "www.reddit.com",
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "workable.com",
    "angel.co", "wellfound.com", "indeed.com", "glassdoor.com",
    "arxiv.org", "grnh.se", "lnkd.in", "t.co", "goo.gl", "tinyurl.com",
    "calendly.com", "cal.com", "zoom.us", "schema.org", "w3.org",
})

JOB_BOARD_HOST_RE = re.compile(
    r"(greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com|workable\.com|grnh\.se|"
    r"jobs\.(?:eu|us)\.lever\.co|boards\.greenhouse\.io)$",
    re.I,
)


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = unescape(text)
    # HN comments often use bare <p> with no closing tag.
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "\n", text)
    text = re.sub(r"(?i)</li>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "• ", text)
    text = re.sub(r"(?i)<a\s+[^>]*href=['\"]([^'\"]+)['\"][^>]*>", r"\1 ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def first_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def extract_emails(text: str) -> list[str]:
    found = []
    seen = set()
    for match in EMAIL_RE.findall(text or ""):
        email = match.strip().strip(".,);")
        lower = email.lower()
        if lower.endswith((".png", ".jpg", ".gif", ".svg")):
            continue
        if "noreply" in lower or "example.com" in lower:
            continue
        if lower not in seen:
            seen.add(lower)
            found.append(email)
    return found


def extract_urls(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s<>\")\]]+", text or "")
    cleaned = []
    for url in urls:
        url = url.rstrip(".,);\"'")
        if url not in cleaned:
            cleaned.append(url)
    return cleaned


def registrable_domain(host: str) -> str:
    host = (host or "").lower().strip().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def domain_from_url(url: str) -> str:
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return registrable_domain(host)


def is_skip_domain(domain: str) -> bool:
    domain = registrable_domain(domain)
    if not domain:
        return True
    if domain in SKIP_DOMAINS:
        return True
    if JOB_BOARD_HOST_RE.search(domain):
        return True
    # subdomains of skipped hosts
    return any(domain.endswith("." + d) for d in SKIP_DOMAINS)


def company_domain_from_urls(urls: list[str]) -> str:
    """Prefer a real company site over job boards and social links."""
    fallback = ""
    for url in urls:
        domain = domain_from_url(url)
        if not domain or is_skip_domain(domain):
            if not fallback and domain and not domain.endswith("google.com"):
                # keep a job-board host only as last resort if nothing else appears
                continue
            continue
        return domain
    return fallback


def domain_from_email(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return registrable_domain(email.rsplit("@", 1)[-1])
