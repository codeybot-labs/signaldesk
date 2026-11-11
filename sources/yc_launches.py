"""New YC companies from the yc-oss changes/latest snapshot (added list)."""

from __future__ import annotations

from typing import Any, Optional

from httputil import get_json
from sources.base import RawSignal, SourceMeta
from textutil import domain_from_url, is_skip_domain

CHANGES_URL = "https://yc-oss.github.io/api/companies/changes/latest.json"


class YCLaunchesSource:
    meta = SourceMeta(
        id="yc_launches",
        name="New YC companies",
        signal_type="launch",
        description="Companies in the 'added' list of the public yc-oss changes/latest.json feed.",
        limits="Static JSON change feed. Use added[] only as a launch signal; do not republish the corpus.",
    )

    def available(self) -> tuple[bool, str]:
        return True, "keyless yc-oss changes feed"

    def fetch(self) -> list[Any]:
        data = get_json(CHANGES_URL, fixture_name="yc_changes_latest.json") or {}
        added = data.get("added") or []
        generated = data.get("generated_at") or ""
        out = []
        for item in added:
            if isinstance(item, dict):
                row = dict(item)
                row["_generated_at"] = generated
                out.append(row)
        return out

    def normalize(self, raw: Any) -> Optional[RawSignal]:
        if not isinstance(raw, dict):
            return None
        name = (raw.get("name") or "").strip()
        if not name:
            return None
        website = raw.get("website") or ""
        domain = domain_from_url(website) or ""
        if domain and is_skip_domain(domain):
            domain = ""
        one = (raw.get("one_liner") or "").strip()
        batch = raw.get("batch") or ""
        industry = raw.get("industry") or ""
        location = raw.get("all_locations") or ""
        quote = " — ".join(bit for bit in (one, f"new on YC {batch}" if batch else "new on the YC directory", industry) if bit)[:280]
        yc_url = raw.get("url") or ""
        slug = raw.get("slug") or ""
        if not yc_url and slug:
            yc_url = f"https://www.ycombinator.com/companies/{slug}"
        return RawSignal(
            company=name,
            domain=domain,
            signal_type="launch",
            signal_quote=quote,
            source_url=yc_url or website,
            source_id=f"yc-launch-{raw.get('id') or slug or name}",
            contact="",
            role="",
            location=location,
            remote=None,
            tags=["yc", "launch"],
            provenance={
                "source": "yc_launches",
                "yc_id": raw.get("id"),
                "batch": batch,
                "industry": industry,
                "website": website,
                "generated_at": raw.get("_generated_at") or "",
            },
        )
