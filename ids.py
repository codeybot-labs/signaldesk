"""Stable lead identifiers."""

from __future__ import annotations

import hashlib


def make_lead_id(domain: str = "", source_id: str = "", company: str = "") -> str:
    key = (domain or source_id or company or "unknown").strip().lower()
    return "sd-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
