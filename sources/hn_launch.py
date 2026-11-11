"""Launch HN posts via Algolia: YC companies announcing themselves (launch signals)."""

from __future__ import annotations

import re
from typing import Any, Optional

from httputil import get_json
from sources.base import RawSignal, SourceMeta
from textutil import company_domain_from_urls, domain_from_url, is_skip_domain, strip_html

SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22Launch%20HN%22&tags=story&hitsPerPage=50"
)
TITLE_RE = re.compile(r"^\s*Launch\s+HN\s*:\s*(.+)$", re.I)
BATCH_RE = re.compile(r"\(\s*YC\s+([A-Z]\d{2})\s*\)", re.I)


def parse_title(title: str) -> tuple[str, str, str]:
    """'Launch HN: Rivet (YC W23) – Scale agents' -> ('Rivet', 'W23', 'Scale agents')."""
    m = TITLE_RE.match(title or "")
    if not m:
        return "", "", ""
    rest = m.group(1).strip()
    batch = ""
    bm = BATCH_RE.search(rest)
    if bm:
        batch = bm.group(1).upper()
        name = rest[: bm.start()].strip()
        desc = rest[bm.end():].strip(" –—-:,")
    else:
        name, desc = rest, ""
        for sep in (" – ", " — ", " - ", ": "):
            if sep in rest:
                name, desc = rest.split(sep, 1)
                break
    return name.strip()[:80], batch, desc.strip()


class HNLaunchSource:
    meta = SourceMeta(
        id="hn_launch",
        name="Launch HN",
        signal_type="launch",
        description="Launch HN posts: YC startups introducing their product on Hacker News.",
        limits="Algolia HN Search, 10k requests/hour/IP.",
    )

    def available(self) -> tuple[bool, str]:
        return True, "keyless public Algolia HN Search"

    def fetch(self) -> list[Any]:
        data = get_json(SEARCH_URL, fixture_name="hn_launch_search.json")
        return (data or {}).get("hits") or []

    def normalize(self, raw: Any) -> Optional[RawSignal]:
        if not isinstance(raw, dict):
            return None
        company, batch, desc = parse_title(raw.get("title") or "")
        if not company:
            return None
        url = raw.get("url") or ""
        domain = domain_from_url(url) if url else ""
        if domain and is_skip_domain(domain):
            domain = company_domain_from_urls([url]) or ""
        object_id = str(raw.get("objectID") or raw.get("story_id") or "")
        quote = desc or strip_html(raw.get("story_text") or "")[:160] or raw.get("title", "")
        return RawSignal(
            company=company,
            domain=domain,
            signal_type="launch",
            signal_quote=(f"Launch HN (YC {batch}): " if batch else "Launch HN: ") + quote[:150],
            source_url=f"https://news.ycombinator.com/item?id={object_id}" if object_id else url,
            source_id=f"hn-launch-{object_id or company}",
            tags=["hn", "launch", "launchhn"] + ([f"yc-{batch.lower()}"] if batch else []),
            provenance={
                "source": "hn_launch",
                "object_id": object_id,
                "batch": batch,
                "author": raw.get("author") or "",
                "points": raw.get("points"),
                "url": url,
            },
        )
