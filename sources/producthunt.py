"""Optional Product Hunt source. Disabled unless PRODUCTHUNT_TOKEN is set.

Product Hunt's API terms restrict commercial use; do not enable this
source for a commercial product without permission from Product Hunt.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from httputil import post_json, USER_AGENT
from sources.base import RawSignal, SourceMeta
from textutil import domain_from_url, is_skip_domain

PH_URL = "https://api.producthunt.com/v2/api/graphql"
PH_QUERY = """
query SignalDeskPosts {
  posts(first: 20, order: NEWEST) {
    edges {
      node {
        id
        name
        tagline
        url
        website
        slug
        votesCount
      }
    }
  }
}
"""


def _token() -> str:
    # Only Hermes secret_scope. Do not fall back to process env, which can
    # pick up another profile's token under a multi-profile gateway.
    try:
        from agent.secret_scope import get_secret
        return (get_secret("PRODUCTHUNT_TOKEN") or "").strip()
    except Exception:
        return ""


def build():
    return ProductHuntSource()


class ProductHuntSource:
    meta = SourceMeta(
        id="producthunt",
        name="Product Hunt",
        signal_type="launch",
        requires_env=["PRODUCTHUNT_TOKEN"],
        description="Newest Product Hunt posts via official GraphQL v2. Optional; off when no token is set.",
        limits="Requires a Product Hunt developer token. API terms restrict commercial use without permission.",
    )

    def available(self) -> tuple[bool, str]:
        if not _token():
            return False, "optional — set PRODUCTHUNT_TOKEN through Hermes secret_scope to enable"
        return True, "Product Hunt GraphQL v2 (token present)"

    def fetch(self) -> list[Any]:
        token = _token()
        if not token:
            return []
        # Fixture hook: if SIGNALDESK_FIXTURE_DIR has producthunt.json, httputil can't
        # serve it via post_json, so read it here when offline.
        if os.environ.get("SIGNALDESK_OFFLINE"):
            from httputil import fixture_dir
            fix = fixture_dir()
            if fix and (fix / "producthunt.json").is_file():
                import json
                data = json.loads((fix / "producthunt.json").read_text(encoding="utf-8"))
                return _edges(data)
            return []
        data = post_json(
            PH_URL,
            {"query": PH_QUERY},
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )
        return _edges(data)

    def normalize(self, raw: Any) -> Optional[RawSignal]:
        if not isinstance(raw, dict):
            return None
        node = raw.get("node") if "node" in raw else raw
        if not isinstance(node, dict):
            return None
        name = (node.get("name") or "").strip()
        if not name:
            return None
        website = node.get("website") or node.get("websiteUrl") or ""
        domain = domain_from_url(website) or ""
        if domain and is_skip_domain(domain):
            domain = ""
        tagline = (node.get("tagline") or "").strip()
        url = node.get("url") or (f"https://www.producthunt.com/posts/{node['slug']}" if node.get("slug") else website)
        return RawSignal(
            company=name,
            domain=domain,
            signal_type="launch",
            signal_quote=tagline or f"{name} launched on Product Hunt",
            source_url=url,
            source_id=f"ph-{node.get('id') or node.get('slug') or name}",
            tags=["producthunt", "launch"],
            provenance={
                "source": "producthunt",
                "votes": node.get("votesCount"),
                "website": website,
            },
        )


def _edges(data: Any) -> list[Any]:
    if not isinstance(data, dict):
        return []
    posts = (data.get("data") or {}).get("posts") or data.get("posts") or {}
    return list(posts.get("edges") or [])
