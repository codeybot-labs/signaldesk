"""Transparent ICP scoring. Returns (score 0-100, list of reasons)."""

from __future__ import annotations

from models import ICP, Lead


def _hay(lead: Lead) -> str:
    parts = [
        lead.company, lead.role, lead.location, lead.signal_quote,
        lead.domain, " ".join(lead.tags or []),
        " ".join(str(v) for v in (lead.provenance or {}).values() if isinstance(v, str)),
    ]
    return " ".join(p or "" for p in parts).lower()


def _tokens(values: list[str]) -> list[str]:
    out = []
    for v in values or []:
        v = (v or "").strip().lower()
        if v:
            out.append(v)
    return out


def _contains(hay: str, needle: str) -> bool:
    needle = needle.lower().strip()
    if not needle:
        return False
    return needle in hay


def score_lead(lead: Lead, icp: ICP) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 10  # base: it is a real public signal
    reasons.append(f"public {lead.signal_type or 'signal'} source")
    hay = _hay(lead)

    kws = _tokens(icp.keywords)
    if kws:
        hits = [k for k in kws if _contains(hay, k)]
        if hits:
            add = min(30, 10 * len(hits))
            score += add
            reasons.append("keywords matched: " + ", ".join(hits[:6]))
        else:
            score -= 5
            reasons.append("no ICP keywords in the signal")

    roles = _tokens(list(icp.roles or []) + list(icp.stack or []))
    if roles:
        hits = [r for r in roles if _contains(hay, r)]
        if hits:
            score += min(20, 8 * len(hits))
            reasons.append("role/stack matched: " + ", ".join(hits[:6]))

    locs = _tokens(icp.locations)
    remote = lead.remote
    loc_hit = False
    if locs:
        loc_hit = any(_contains(hay, loc) for loc in locs)
        if loc_hit:
            score += 10
            reasons.append("location matched ICP")
    if remote is True and icp.remote_ok:
        score += 8
        reasons.append("remote role (ICP allows remote)")
        loc_hit = True
    if remote is False and icp.onsite_ok and loc_hit:
        score += 4
        reasons.append("onsite role in a matching location")
    if remote is False and not icp.onsite_ok:
        score -= 15
        reasons.append("onsite-only role but ICP prefers remote")
    if remote is True and not icp.remote_ok:
        score -= 10
        reasons.append("remote role but ICP prefers onsite")

    stages = _tokens(icp.company_stage)
    if stages:
        hits = [s for s in stages if _contains(hay, s)]
        if hits:
            score += 8
            reasons.append("stage matched: " + ", ".join(hits))

    exclusions = _tokens(icp.exclusions)
    if exclusions:
        hits = [e for e in exclusions if _contains(hay, e)]
        if hits:
            score -= 40
            reasons.append("excluded term: " + ", ".join(hits[:4]))

    if lead.contact:
        score += 6
        reasons.append("public contact in the source")
    if lead.mx_ok is True:
        score += 4
        reasons.append("domain publishes MX")
    elif lead.mx_ok is False:
        reasons.append("no MX record for domain")

    score = max(0, min(100, score))
    return score, reasons
