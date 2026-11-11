"""Recent Show HN posts via Algolia (launch / builder signals)."""

from __future__ import annotations

import re
from typing import Any, Optional

from httputil import get_json
from sources.base import RawSignal, SourceMeta
from textutil import company_domain_from_urls, domain_from_url, is_skip_domain, strip_html

SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=Show%20HN&tags=story&hitsPerPage=50"
)
TITLE_RE = re.compile(r"^\s*Show\s+HN\s*:\s*(.+)$", re.I)


def _company_from_title(title: str) -> tuple[str, str]:
    title = (title or "").strip()
    m = TITLE_RE.match(title)
    rest = m.group(1).strip() if m else title
    # "Name – description" or "Name: description" or "Name, description"
    for sep in (" – ", " — ", " - ", ": ", ", "):
        if sep in rest:
            name, desc = rest.split(sep, 1)
            name = name.strip()
            if 1 < len(name) <= 80:
                return name, desc.strip()
    return rest[:80], rest


class HNShowSource:
    meta = SourceMeta(
        id="hn_show",
        name="Show HN",
        signal_type="launch",
        description="Fresh Show HN posts — indie launches and new products.",
        limits="Algolia HN Search, 10k requests/hour/IP.",
    )

    def available(self) -> tuple[bool, str]:
        return True, "keyless public Algolia HN Search"

    def fetch(self) -> list[Any]:
        data = get_json(SEARCH_URL, fixture_name="hn_show_search.json")
        return (data or {}).get("hits") or []

    def normalize(self, raw: Any) -> Optional[RawSignal]:
        if not isinstance(raw, dict):
            return None
        title = raw.get("title") or ""
        if not TITLE_RE.match(title):
            return None
        company, rest = _company_from_title(title)
        if not company:
            return None
        url = raw.get("url") or ""
        domain = domain_from_url(url) if url else ""
        if domain and is_skip_domain(domain):
            domain = company_domain_from_urls([url]) or ""
        object_id = str(raw.get("objectID") or raw.get("story_id") or "")
        source_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else url
        story_text = strip_html(raw.get("story_text") or "")
        quote = rest or story_text
        if story_text and rest and rest not in story_text:
            quote = f"{rest} — {story_text}"
        quote = (quote or title)[:280]
        return RawSignal(
            company=company,
            domain=domain,
            signal_type="launch",
            signal_quote=quote,
            source_url=source_url,
            source_id=f"hn-show-{object_id or company}",
            contact="",
            role="",
            location="",
            remote=None,
            tags=["hn", "launch", "showhn"],
            provenance={
                "source": "hn_show",
                "object_id": object_id,
                "author": raw.get("author") or "",
                "points": raw.get("points"),
                "url": url,
            },
        )
