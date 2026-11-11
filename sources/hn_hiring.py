"""Hacker News 'Who is hiring?' monthly thread via Algolia (keyless)."""

from __future__ import annotations

from typing import Any, Optional

from httputil import get_json
from parse_hiring import parse_comment
from sources.base import RawSignal, SourceMeta
from textutil import company_domain_from_urls

SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?tags=story,author_whoishiring&hitsPerPage=5"
)
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"


class HNHiringSource:
    meta = SourceMeta(
        id="hn_hiring",
        name="HN Who is hiring?",
        signal_type="hiring",
        description="Top-level comments from the current official 'Ask HN: Who is hiring?' thread.",
        limits="Algolia HN Search, 10k requests/hour/IP. Public comments only.",
    )

    def available(self) -> tuple[bool, str]:
        return True, "keyless public Algolia HN Search"

    def fetch(self) -> list[Any]:
        search = get_json(SEARCH_URL, fixture_name="hn_whoishiring_search.json")
        hits = (search or {}).get("hits") or []
        if not hits:
            return []
        thread_id = str(hits[0].get("objectID") or hits[0].get("story_id") or "")
        if not thread_id:
            return []
        thread = get_json(ITEM_URL.format(id=thread_id), fixture_name="hn_hiring_thread.json")
        children = (thread or {}).get("children") or []
        # Algolia items API returns top-level comments as children
        out = []
        for child in children:
            if not isinstance(child, dict):
                continue
            child = dict(child)
            child["_thread_id"] = thread_id
            child["_thread_title"] = (thread or {}).get("title") or ""
            out.append(child)
        return out

    def normalize(self, raw: Any) -> Optional[RawSignal]:
        if not isinstance(raw, dict):
            return None
        parsed = parse_comment(raw.get("text") or raw.get("comment_text") or "")
        if not parsed:
            return None
        domain = parsed.get("domain") or ""
        urls = parsed.get("urls") or []
        if not domain:
            domain = company_domain_from_urls(urls) or ""
        thread_id = raw.get("_thread_id") or ""
        comment_id = str(raw.get("id") or raw.get("objectID") or "")
        source_url = ""
        if comment_id:
            source_url = f"https://news.ycombinator.com/item?id={comment_id}"
        elif thread_id:
            source_url = f"https://news.ycombinator.com/item?id={thread_id}"
        return RawSignal(
            company=parsed["company"],
            domain=domain,
            signal_type="hiring",
            signal_quote=parsed.get("signal_quote") or "",
            source_url=source_url,
            source_id=f"hn-hiring-{comment_id or parsed['company']}",
            contact=parsed.get("contact") or "",
            role=parsed.get("role") or "",
            location=parsed.get("location") or "",
            remote=parsed.get("remote"),
            tags=["hn", "hiring"],
            provenance={
                "source": "hn_hiring",
                "thread_id": thread_id,
                "comment_id": comment_id,
                "author": raw.get("author") or "",
                "thread_title": raw.get("_thread_title") or "",
            },
        )
