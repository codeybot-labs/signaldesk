"""Scan orchestration: fetch → normalize → MX → score → upsert."""

from __future__ import annotations

import os
from typing import Any, Optional

from icp import load_icp
from ids import make_lead_id
from models import ICP, Lead
from mx import lookup_mx
from score import score_lead
from sources import sources_for
from sources.base import RawSignal
from store import upsert_new_lead
from textutil import is_skip_domain


def _skip_mx() -> bool:
    return os.environ.get("SIGNALDESK_SKIP_MX", "").strip() in {"1", "true", "yes"}


def raw_to_lead(raw: RawSignal, icp: ICP) -> Optional[Lead]:
    domain = (raw.domain or "").lower().strip()
    if domain and is_skip_domain(domain):
        # job boards / public hosts are not a company inbox
        domain = ""
    if not raw.company:
        return None
    mx_ok = None
    if domain and not _skip_mx():
        try:
            mx_ok = lookup_mx(domain)
        except Exception:
            mx_ok = None
    lead = Lead(
        id=make_lead_id(domain, raw.source_id, raw.company),
        company=raw.company,
        domain=domain,
        signal_type=raw.signal_type,
        signal_quote=raw.signal_quote,
        source_url=raw.source_url,
        source_id=raw.source_id,
        contact=raw.contact or "",
        role=raw.role or "",
        location=raw.location or "",
        remote=raw.remote,
        mx_ok=mx_ok,
        tags=list(raw.tags or []),
        provenance=dict(raw.provenance or {}),
        stage="new",
    )
    score, reasons = score_lead(lead, icp)
    lead.score = score
    lead.score_reasons = reasons
    if score >= int(icp.qualify_min_score or 0):
        lead.stage = "qualified"
    return lead


def scan(kind: str = "all", icp: Optional[ICP] = None, limit_per_source: int = 200) -> dict[str, Any]:
    """Run enabled sources and upsert leads. Never raises."""
    icp = icp or load_icp()
    report: dict[str, Any] = {
        "ok": True,
        "kind": kind,
        "sources": [],
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "qualified": 0,
    }
    try:
        srcs = sources_for(kind)
    except Exception as exc:
        return {"ok": False, "error": f"source registry failed: {exc}"}
    if not srcs:
        report["ok"] = False
        report["error"] = f"no sources matched kind={kind!r}"
        return report

    for src in srcs:
        row: dict[str, Any] = {"id": src.meta.id, "name": src.meta.name, "fetched": 0, "kept": 0}
        try:
            ok, reason = src.available()
            row["enabled"] = ok
            row["message"] = reason
            if not ok:
                report["sources"].append(row)
                continue
            raw_items = src.fetch() or []
            row["fetched"] = len(raw_items)
            kept = 0
            for raw in raw_items[: int(limit_per_source)]:
                try:
                    normalized = src.normalize(raw)
                    if not normalized:
                        report["skipped"] += 1
                        continue
                    lead = raw_to_lead(normalized, icp)
                    if not lead:
                        report["skipped"] += 1
                        continue
                    saved, action = upsert_new_lead(lead)
                    if action == "inserted":
                        report["inserted"] += 1
                    else:
                        report["updated"] += 1
                    if saved.stage == "qualified" or saved.score >= int(icp.qualify_min_score or 0):
                        report["qualified"] += 1
                    kept += 1
                except Exception as exc:
                    report["errors"].append(f"{src.meta.id}: {exc}")
                    report["skipped"] += 1
            row["kept"] = kept
        except Exception as exc:
            row["error"] = str(exc)
            report["errors"].append(f"{src.meta.id}: {exc}")
        report["sources"].append(row)
    return report
