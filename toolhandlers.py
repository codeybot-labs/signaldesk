"""Tool handlers. Always return JSON strings. Never raise. Never print secrets."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from boardhtml import render_board
from drafts import compose_draft
from icp import load_icp, update_icp
from models import SENDABLE_STAGES, STAGES, Lead
from paths import exports_dir
from pipeline import map_scan as run_map_scan
from pipeline import scan as run_scan
from sources import list_source_info
from store import counts_by_stage, get_lead, list_leads, save_lead

# Set by register() so drafts can use the host LLM when present.
_CTX: Any = None


def set_context(ctx: Any) -> None:
    global _CTX
    _CTX = ctx


def _ok(**kwargs) -> str:
    return json.dumps(kwargs, default=str)


def _err(msg: str, **kwargs) -> str:
    payload = {"ok": False, "error": msg}
    payload.update(kwargs)
    return json.dumps(payload, default=str)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_dt(val: str) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None


def _lead_public(lead: Lead) -> dict:
    return lead.to_public_dict()


def signaldesk_set_icp(args: dict, **kwargs) -> str:
    try:
        args = args or {}
        icp = update_icp(args)
        return _ok(ok=True, icp=icp.to_dict())
    except Exception as exc:
        return _err(f"Failed to save ICP: {exc}")


def signaldesk_scan(args: dict, **kwargs) -> str:
    try:
        kind = (args or {}).get("kind") or "all"
        report = run_scan(kind=str(kind))
        report["counts"] = counts_by_stage()
        # refresh board after a scan so the UI stays current
        try:
            report["board"] = str(render_board())
        except Exception:
            pass
        return json.dumps(report, default=str)
    except Exception as exc:
        return _err(f"Scan failed: {exc}")


def signaldesk_map_scan(args: dict, **kwargs) -> str:
    """LocalLead Map: businesses from OpenStreetMap (Overpass + Nominatim) -> scored leads."""
    try:
        args = args or {}
        city = str(args.get("city") or "").strip()
        btype = str(args.get("business_type") or args.get("type") or "").strip()
        bbox = args.get("bbox")
        if not btype:
            return _err("business_type is required, e.g. 'dentist' or 'cafe'.")
        if not city and not bbox:
            return _err("Pass a city name or a bbox (south,west,north,east).")
        report = run_map_scan(city=city, business_type=btype, bbox=bbox,
                              limit=int(args.get("limit") or 40))
        report["counts"] = counts_by_stage()
        report["message"] = ("Leads saved and scored. Nothing was drafted or sent. "
                             + report["attribution"])
        try:
            render_board()
        except Exception:
            pass
        return json.dumps(report, default=str)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Map scan failed: {exc}")


def signaldesk_list(args: dict, **kwargs) -> str:
    try:
        args = args or {}
        limit = int(args.get("limit") or 25)
        leads = list_leads(stage=args.get("stage") or None,
                           signal_type=args.get("signal_type") or None,
                           limit=max(1, min(limit, 200)))
        return _ok(ok=True, count=len(leads), counts=counts_by_stage(),
                   leads=[_lead_public(l) for l in leads])
    except Exception as exc:
        return _err(f"List failed: {exc}")


def signaldesk_draft(args: dict, **kwargs) -> str:
    try:
        lead_id = (args or {}).get("lead_id") or ""
        lead = get_lead(lead_id)
        if not lead:
            return _err("Lead not found", lead_id=lead_id)
        if lead.stage in {"sent", "won", "lost"}:
            return _err(f"Lead is already {lead.stage}; not redrafting automatically.", lead_id=lead_id)
        icp = load_icp()
        llm = None
        try:
            llm = getattr(_CTX, "llm", None) if _CTX is not None else None
        except Exception:
            llm = None
        subject, body, method = compose_draft(lead, icp, llm=llm)
        lead.draft_subject = subject
        lead.draft_body = body
        if lead.stage in {"new", "qualified"}:
            lead.stage = "drafted"
        save_lead(lead)
        return _ok(ok=True, method=method, lead=_lead_public(lead))
    except Exception as exc:
        return _err(f"Draft failed: {exc}")


def signaldesk_approve(args: dict, **kwargs) -> str:
    try:
        lead_id = (args or {}).get("lead_id") or ""
        lead = get_lead(lead_id)
        if not lead:
            return _err("Lead not found", lead_id=lead_id)
        if not lead.draft_body:
            return _err("Draft this lead before approving it.", lead_id=lead_id)
        lead.stage = "approved"
        lead.approved_at = _now()
        save_lead(lead)
        return _ok(ok=True, message="Approved. Nothing was sent. Use signaldesk_prepare_send when you are ready.",
                   lead=_lead_public(lead))
    except Exception as exc:
        return _err(f"Approve failed: {exc}")


def signaldesk_mark(args: dict, **kwargs) -> str:
    try:
        args = args or {}
        lead = get_lead(args.get("lead_id") or "")
        if not lead:
            return _err("Lead not found")
        stage = (args.get("stage") or "").strip().lower()
        if stage:
            if stage not in STAGES:
                return _err(f"Unknown stage {stage!r}", allowed=list(STAGES))
            lead.stage = stage
            if stage == "sent" and not lead.sent_at:
                lead.sent_at = _now()
            if stage == "approved" and not lead.approved_at:
                lead.approved_at = _now()
        if args.get("followed_up"):
            if lead.stage not in {"sent", "replied"}:
                return _err("Only sent leads can be marked as followed up.", stage=lead.stage)
            lead.last_followup_at = _now()
        if args.get("notes"):
            lead.notes = str(args["notes"])
        save_lead(lead)
        return _ok(ok=True, lead=_lead_public(lead))
    except Exception as exc:
        return _err(f"Mark failed: {exc}")


def signaldesk_followups(args: dict, **kwargs) -> str:
    try:
        icp = load_icp()
        days = int(icp.followup_days or 5)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        limit = int((args or {}).get("limit") or 20)
        due = []
        for lead in list_leads(stage="sent", limit=200):
            stamp = _parse_dt(lead.last_followup_at) or _parse_dt(lead.sent_at)
            if stamp is None or stamp <= cutoff:
                row = _lead_public(lead)
                row["days_since_contact"] = (
                    int((datetime.now(timezone.utc) - stamp).total_seconds() // 86400) if stamp else None)
                due.append(row)
            if len(due) >= limit:
                break
        return _ok(ok=True, followup_days=days, count=len(due), leads=due)
    except Exception as exc:
        return _err(f"Followups failed: {exc}")


def signaldesk_export_csv(args: dict, **kwargs) -> str:
    try:
        args = args or {}
        leads = list_leads(stage=args.get("stage") or None,
                           signal_type=args.get("signal_type") or None,
                           limit=2000)
        dest = exports_dir() / f"leads-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
        fields = [
            "id", "company", "domain", "signal_type", "score", "stage", "role",
            "location", "contact", "phone", "website", "lat", "lon", "source_url",
            "signal_quote", "draft_subject", "approved_at", "sent_at", "attribution",
        ]
        has_osm = False
        with dest.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for lead in leads:
                row = lead.to_public_dict()
                prov = lead.provenance or {}
                for key in ("phone", "website", "lat", "lon"):
                    row[key] = prov.get(key, "")
                row["attribution"] = _attribution(lead)
                has_osm = has_osm or bool(row["attribution"])
                writer.writerow({k: row.get(k, "") for k in fields})
            if has_osm:
                # Footer row so the notice survives even if the column is dropped.
                writer.writerow({"id": "#", "company": "Map data " + OSM_ATTRIBUTION})
        return _ok(ok=True, path=str(dest), count=len(leads),
                   attribution=OSM_ATTRIBUTION if has_osm else "")
    except Exception as exc:
        return _err(f"Export failed: {exc}")


def signaldesk_sources(args: dict, **kwargs) -> str:
    try:
        return _ok(ok=True, sources=list_source_info())
    except Exception as exc:
        return _err(f"Sources failed: {exc}")


OSM_ATTRIBUTION = "© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)"


def _attribution(lead: Lead) -> str:
    prov = lead.provenance or {}
    if lead.signal_type == "local" or prov.get("source") == "osm_map":
        return OSM_ATTRIBUTION
    return ""


def _write_eml(lead: Lead, dest: Path) -> Path:
    to_addr = lead.contact or ""
    subject = lead.draft_subject or f"Regarding {lead.company}"
    body = lead.draft_body or ""
    # RFC 5322-ish .eml, 7-bit. Keep it simple and local.
    lines = [
        f"To: {to_addr}" if to_addr else "To: ",
        f"Subject: {subject}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "X-SignalDesk-Lead: " + lead.id,
        "X-SignalDesk-Source: " + (lead.source_url or ""),
    ]
    if _attribution(lead):
        lines.append("X-SignalDesk-Data-Attribution: " + _attribution(lead))
    lines += [
        "",
        body,
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def signaldesk_prepare_send(args: dict, **kwargs) -> str:
    try:
        lead = get_lead((args or {}).get("lead_id") or "")
        if not lead:
            return _err("Lead not found")
        if lead.stage not in SENDABLE_STAGES and lead.stage != "approved":
            return _err(
                "Lead is not approved. Call signaldesk_approve first. Nothing was written or sent.",
                stage=lead.stage,
            )
        if not lead.draft_body:
            return _err("No draft body on this lead.")
        dest = exports_dir() / f"{lead.id}.eml"
        _write_eml(lead, dest)
        mailto = ""
        if lead.contact:
            mailto = (
                f"mailto:{quote(lead.contact)}?subject={quote(lead.draft_subject or '')}"
                f"&body={quote(lead.draft_body[:1800])}"
            )
        return _ok(
            ok=True,
            sent=False,
            message="Local .eml written. Open it in your mail client or copy the body. SignalDesk did not send anything.",
            eml_path=str(dest),
            mailto=mailto,
            to=lead.contact or "",
            subject=lead.draft_subject,
            body=lead.draft_body,
        )
    except Exception as exc:
        return _err(f"Prepare send failed: {exc}")


def signaldesk_board(args: dict, **kwargs) -> str:
    try:
        dest = (args or {}).get("path")
        path = render_board(Path(dest) if dest else None)
        return _ok(ok=True, path=str(path))
    except Exception as exc:
        return _err(f"Board render failed: {exc}")


HANDLERS = {
    "signaldesk_set_icp": signaldesk_set_icp,
    "signaldesk_scan": signaldesk_scan,
    "signaldesk_list": signaldesk_list,
    "signaldesk_draft": signaldesk_draft,
    "signaldesk_approve": signaldesk_approve,
    "signaldesk_mark": signaldesk_mark,
    "signaldesk_followups": signaldesk_followups,
    "signaldesk_export_csv": signaldesk_export_csv,
    "signaldesk_sources": signaldesk_sources,
    "signaldesk_prepare_send": signaldesk_prepare_send,
    "signaldesk_board": signaldesk_board,
    "signaldesk_map_scan": signaldesk_map_scan,
}
