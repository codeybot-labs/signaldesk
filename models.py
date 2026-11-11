"""Lead and ICP records for SignalDesk."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any, Optional

STAGES = (
    "new",
    "qualified",
    "drafted",
    "approved",
    "sent",
    "replied",
    "won",
    "lost",
)

SIGNAL_TYPES = ("hiring", "launch", "local")

# Stages that mean the user already approved outreach to this lead.
SENDABLE_STAGES = frozenset({"approved", "sent", "replied", "won"})


@dataclass
class ICP:
    keywords: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    stack: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    remote_ok: bool = True
    onsite_ok: bool = True
    company_stage: list[str] = field(default_factory=list)  # e.g. seed, early, growth
    exclusions: list[str] = field(default_factory=list)
    offer: str = ""
    business_types: list[str] = field(default_factory=list)  # LocalLead Map, e.g. dentist, cafe
    local_offer: str = ""  # optional pitch for local businesses (falls back to offer)
    booking_link: str = ""
    sender_name: str = ""
    qualify_min_score: int = 35
    followup_days: int = 5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict[str, Any]]) -> "ICP":
        if not data:
            return cls()
        allowed = {f.name for f in fields(cls)}
        clean = {}
        for key, val in data.items():
            if key not in allowed:
                continue
            if key in {"keywords", "roles", "stack", "locations", "company_stage", "exclusions", "business_types"}:
                if isinstance(val, str):
                    val = [p.strip() for p in val.split(",") if p.strip()]
                elif not isinstance(val, list):
                    val = []
                else:
                    val = [str(x).strip() for x in val if str(x).strip()]
            elif key in {"remote_ok", "onsite_ok"}:
                val = bool(val)
            elif key in {"qualify_min_score", "followup_days"}:
                try:
                    val = int(val)
                except (TypeError, ValueError):
                    continue
            elif val is None:
                val = ""
            else:
                val = str(val)
            clean[key] = val
        return cls(**clean)


@dataclass
class Lead:
    id: str
    company: str
    domain: str
    signal_type: str
    signal_quote: str
    source_url: str
    source_id: str = ""
    contact: str = ""
    role: str = ""
    location: str = ""
    remote: Optional[bool] = None
    mx_ok: Optional[bool] = None
    score: int = 0
    score_reasons: list[str] = field(default_factory=list)
    stage: str = "new"
    draft_subject: str = ""
    draft_body: str = ""
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    approved_at: str = ""
    sent_at: str = ""
    last_followup_at: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # never include secrets; there are none on the record, but keep the door closed
        return d
