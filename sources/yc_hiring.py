"""YC companies currently hiring, from the keyless yc-oss static API."""

from __future__ import annotations

from typing import Any, Optional

from httputil import get_json
from sources.base import RawSignal, SourceMeta
from textutil import domain_from_url, is_skip_domain

HIRING_URL = "https://yc-oss.github.io/api/companies/hiring.json"


class YCHiringSource:
    meta = SourceMeta(
        id="yc_hiring",
        name="YC companies hiring",
        signal_type="hiring",
        description="Companies flagged isHiring in the public yc-oss snapshot of the YC directory.",
        limits="Static JSON; do not republish the corpus. Use the API, attribute YC / yc-oss.",
    )

    def available(self) -> tuple[bool, str]:
        return True, "keyless yc-oss static JSON"

    def fetch(self) -> list[Any]:
        data = get_json(HIRING_URL, fixture_name="yc_hiring_sample.json")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("companies") or data.get("results") or []
        return []

    def normalize(self, raw: Any) -> Optional[RawSignal]:
        if not isinstance(raw, dict):
            return None
        if raw.get("isHiring") is False:
            return None
        name = (raw.get("name") or "").strip()
        if not name:
            return None
        website = raw.get("website") or ""
        domain = domain_from_url(website) or ""
        if domain and is_skip_domain(domain):
            domain = ""
        one = (raw.get("one_liner") or "").strip()
        industry = raw.get("industry") or ""
        batch = raw.get("batch") or ""
        location = raw.get("all_locations") or ""
        quote_bits = [bit for bit in (one, f"YC {batch}" if batch else "", industry) if bit]
        quote = " — ".join(quote_bits)[:280]
        yc_url = raw.get("url") or ""
        slug = raw.get("slug") or ""
        if not yc_url and slug:
            yc_url = f"https://www.ycombinator.com/companies/{slug}"
        tags = []
        if isinstance(raw.get("tags"), list):
            tags = [str(t) for t in raw["tags"][:8]]
        stage = raw.get("stage") or raw.get("status") or ""
        return RawSignal(
            company=name,
            domain=domain,
            signal_type="hiring",
            signal_quote=quote or f"{name} is hiring",
            source_url=yc_url or website,
            source_id=f"yc-hiring-{raw.get('id') or slug or name}",
            contact="",
            role="",
            location=location,
            remote=None,
            tags=["yc", "hiring"] + tags,
            provenance={
                "source": "yc_hiring",
                "yc_id": raw.get("id"),
                "batch": batch,
                "team_size": raw.get("team_size"),
                "industry": industry,
                "stage": stage,
                "website": website,
            },
        )
