"""SQLite lead store under the plugin data directory."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from models import STAGES, Lead
from paths import data_root

_LOCK = threading.Lock()
_CREATE = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    domain TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    signal_quote TEXT,
    source_url TEXT,
    source_id TEXT,
    contact TEXT,
    role TEXT,
    location TEXT,
    remote INTEGER,
    mx_ok INTEGER,
    score INTEGER DEFAULT 0,
    score_reasons TEXT,
    stage TEXT DEFAULT 'new',
    draft_subject TEXT,
    draft_body TEXT,
    notes TEXT,
    tags TEXT,
    provenance TEXT,
    created_at TEXT,
    updated_at TEXT,
    approved_at TEXT,
    sent_at TEXT,
    last_followup_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(domain);
CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def db_path() -> Path:
    return data_root() / "signaldesk.sqlite"


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_CREATE)
    return conn


def _row_to_lead(row: sqlite3.Row) -> Lead:
    def _json(val, default):
        if not val:
            return default
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return default

    remote = row["remote"]
    mx = row["mx_ok"]
    return Lead(
        id=row["id"],
        company=row["company"] or "",
        domain=row["domain"] or "",
        signal_type=row["signal_type"] or "",
        signal_quote=row["signal_quote"] or "",
        source_url=row["source_url"] or "",
        source_id=row["source_id"] or "",
        contact=row["contact"] or "",
        role=row["role"] or "",
        location=row["location"] or "",
        remote=None if remote is None else bool(remote),
        mx_ok=None if mx is None else bool(mx),
        score=int(row["score"] or 0),
        score_reasons=_json(row["score_reasons"], []),
        stage=row["stage"] or "new",
        draft_subject=row["draft_subject"] or "",
        draft_body=row["draft_body"] or "",
        notes=row["notes"] or "",
        tags=_json(row["tags"], []),
        provenance=_json(row["provenance"], {}),
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
        approved_at=row["approved_at"] or "",
        sent_at=row["sent_at"] or "",
        last_followup_at=row["last_followup_at"] or "",
    )


def _lead_params(lead: Lead) -> dict[str, Any]:
    return {
        "id": lead.id,
        "company": lead.company,
        "domain": lead.domain,
        "signal_type": lead.signal_type,
        "signal_quote": lead.signal_quote,
        "source_url": lead.source_url,
        "source_id": lead.source_id,
        "contact": lead.contact,
        "role": lead.role,
        "location": lead.location,
        "remote": None if lead.remote is None else int(bool(lead.remote)),
        "mx_ok": None if lead.mx_ok is None else int(bool(lead.mx_ok)),
        "score": int(lead.score),
        "score_reasons": json.dumps(lead.score_reasons),
        "stage": lead.stage if lead.stage in STAGES else "new",
        "draft_subject": lead.draft_subject,
        "draft_body": lead.draft_body,
        "notes": lead.notes,
        "tags": json.dumps(lead.tags),
        "provenance": json.dumps(lead.provenance),
        "created_at": lead.created_at,
        "updated_at": lead.updated_at,
        "approved_at": lead.approved_at,
        "sent_at": lead.sent_at,
        "last_followup_at": lead.last_followup_at,
    }


def get_lead(lead_id: str) -> Optional[Lead]:
    with _LOCK:
        conn = connect()
        try:
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            return _row_to_lead(row) if row else None
        finally:
            conn.close()


def find_by_domain(domain: str) -> Optional[Lead]:
    domain = (domain or "").lower().strip()
    if not domain:
        return None
    with _LOCK:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM leads WHERE lower(domain) = ? ORDER BY updated_at DESC LIMIT 1",
                (domain,),
            ).fetchone()
            return _row_to_lead(row) if row else None
        finally:
            conn.close()


def find_by_contact(email: str) -> Optional[Lead]:
    email = (email or "").lower().strip()
    if not email:
        return None
    with _LOCK:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM leads WHERE lower(contact) = ? LIMIT 1", (email,)
            ).fetchone()
            return _row_to_lead(row) if row else None
        finally:
            conn.close()


def find_by_source_id(source_id: str) -> Optional[Lead]:
    source_id = (source_id or "").strip()
    if not source_id:
        return None
    with _LOCK:
        conn = connect()
        try:
            row = conn.execute(
                "SELECT * FROM leads WHERE source_id = ? LIMIT 1", (source_id,)
            ).fetchone()
            return _row_to_lead(row) if row else None
        finally:
            conn.close()


def list_leads(stage: Optional[str] = None, signal_type: Optional[str] = None,
               limit: int = 100) -> list[Lead]:
    q = "SELECT * FROM leads WHERE 1=1"
    args: list[Any] = []
    if stage:
        q += " AND stage = ?"
        args.append(stage)
    if signal_type:
        q += " AND signal_type = ?"
        args.append(signal_type)
    q += " ORDER BY score DESC, updated_at DESC LIMIT ?"
    args.append(int(limit))
    with _LOCK:
        conn = connect()
        try:
            return [_row_to_lead(r) for r in conn.execute(q, args)]
        finally:
            conn.close()


def counts_by_stage() -> dict[str, int]:
    with _LOCK:
        conn = connect()
        try:
            rows = conn.execute("SELECT stage, COUNT(*) AS n FROM leads GROUP BY stage").fetchall()
            out = {s: 0 for s in STAGES}
            for r in rows:
                out[r["stage"]] = r["n"]
            return out
        finally:
            conn.close()


def upsert_new_lead(lead: Lead) -> tuple[Lead, str]:
    """Insert if domain is new; otherwise merge the new signal without downgrading stage.
    Returns (lead, 'inserted'|'updated'|'unchanged')."""
    now = _now()
    existing = find_by_domain(lead.domain) if lead.domain else None
    if existing is None and lead.source_id:
        existing = find_by_source_id(lead.source_id)
    if existing is None and lead.contact:
        existing = find_by_contact(lead.contact)
    if existing is None:
        lead.created_at = lead.created_at or now
        lead.updated_at = now
        with _LOCK:
            conn = connect()
            try:
                cols = _lead_params(lead)
                conn.execute(
                    "INSERT INTO leads (" + ",".join(cols) + ") VALUES ("
                    + ",".join(":" + k for k in cols) + ")",
                    cols,
                )
                conn.commit()
            finally:
                conn.close()
        return lead, "inserted"

    # Merge: keep later pipeline stages; refresh signal if this score is better or quote is new
    existing.signal_quote = existing.signal_quote or lead.signal_quote
    if lead.score > existing.score:
        existing.score = lead.score
        existing.score_reasons = lead.score_reasons
        existing.signal_quote = lead.signal_quote or existing.signal_quote
        existing.source_url = lead.source_url or existing.source_url
        existing.role = lead.role or existing.role
    if lead.contact and not existing.contact:
        existing.contact = lead.contact
    if lead.mx_ok is not None and existing.mx_ok is None:
        existing.mx_ok = lead.mx_ok
    if lead.location and not existing.location:
        existing.location = lead.location
    if existing.remote is None:
        existing.remote = lead.remote
    # provenance: append source
    sources = list(existing.provenance.get("sources") or [])
    if lead.source_id and lead.source_id not in sources:
        sources.append(lead.source_id)
        existing.provenance["sources"] = sources
    existing.updated_at = now
    save_lead(existing)
    return existing, "updated"


def save_lead(lead: Lead) -> Lead:
    lead.updated_at = _now()
    cols = _lead_params(lead)
    with _LOCK:
        conn = connect()
        try:
            assignments = ", ".join(f"{k} = :{k}" for k in cols if k != "id")
            conn.execute(f"UPDATE leads SET {assignments} WHERE id = :id", cols)
            conn.commit()
        finally:
            conn.close()
    return lead


def kv_get(key: str, default: Any = None) -> Any:
    with _LOCK:
        conn = connect()
        try:
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row["value"])
            except json.JSONDecodeError:
                return row["value"]
        finally:
            conn.close()


def kv_set(key: str, value: Any) -> None:
    raw = json.dumps(value)
    with _LOCK:
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, raw),
            )
            conn.commit()
        finally:
            conn.close()
