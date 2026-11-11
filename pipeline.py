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


def poi_to_raw(poi: dict[str, Any], area: str, attribution: str) -> RawSignal:
    """One OpenStreetMap business -> RawSignal (signal_type 'local')."""
    bits = [poi.get("business_type", "").replace("_", " ")]
    if poi.get("address"):
        bits.append(poi["address"])
    if poi.get("opening_hours"):
        bits.append("open " + poi["opening_hours"])
    quote = f"{poi['name']}: " + " · ".join(b for b in bits if b) + " (OpenStreetMap)"
    prov = {k: poi.get(k, "") for k in (
        "lat", "lon", "business_type", "osm_tag", "website", "phone", "address",
        "opening_hours", "osm_type", "osm_id", "osm_url")}
    prov.update({"source": "osm_map", "area": area, "attribution": attribution,
                 "license": "ODbL-1.0"})
    return RawSignal(
        company=poi["name"],
        domain=poi.get("domain", ""),
        signal_type="local",
        signal_quote=quote,
        source_url=poi.get("osm_url", ""),
        source_id=f"osm:{poi.get('osm_type')}/{poi.get('osm_id')}",
        contact=poi.get("email", ""),
        role="",
        location=poi.get("address") or area,
        remote=None,
        tags=["osm_map", poi.get("business_type", "")],
        provenance=prov,
    )


def map_scan(city: str = "", business_type: str = "", bbox: Any = None, limit: int = 40,
             icp: Optional[ICP] = None) -> dict[str, Any]:
    """LocalLead Map: OSM businesses -> scored leads in the same store. Never sends."""
    import geo  # local import keeps hiring/launch scans free of geo deps

    icp = icp or load_icp()
    result = geo.search(city=city, business_type=business_type, bbox=bbox, limit=limit)
    area = result.get("city") or result.get("place") or ""
    report: dict[str, Any] = {
        "ok": True, "mode": result["mode"], "notes": result["notes"], "city": area,
        "business_type": result["business_type"], "osm_tag": result["osm_tag"],
        "bbox": result["bbox"], "attribution": result["attribution"],
        "found": len(result["pois"]), "inserted": 0, "updated": 0, "qualified": 0,
        "errors": [], "leads": [],
    }
    for poi in result["pois"]:
        try:
            lead = raw_to_lead(poi_to_raw(poi, area, result["attribution"]), icp)
            if not lead:
                continue
            saved, action = upsert_new_lead(lead)
            report["inserted" if action == "inserted" else "updated"] += 1
            if saved.stage == "qualified" or saved.score >= int(icp.qualify_min_score or 0):
                report["qualified"] += 1
            prov = saved.provenance or {}
            if any(row["id"] == saved.id for row in report["leads"]):
                continue
            report["leads"].append({
                "id": saved.id, "company": saved.company, "score": saved.score, "stage": saved.stage,
                "lat": prov.get("lat", poi["lat"]), "lon": prov.get("lon", poi["lon"]),
                "website": poi.get("website", ""), "email": poi.get("email", ""),
                "phone": poi.get("phone", ""), "address": poi.get("address", ""),
                "osm_url": poi.get("osm_url", ""),
            })
        except Exception as exc:
            report["errors"].append(f"{poi.get('name')}: {exc}")
    return report
