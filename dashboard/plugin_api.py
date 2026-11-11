"""Dashboard / Desktop backend for SignalDesk. Mounted at /api/plugins/signaldesk/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toolhandlers as tools
from boardhtml import board_payload, render_board

router = APIRouter()


class LeadBody(BaseModel):
    lead_id: str = Field(..., min_length=1)
    stage: str | None = None
    notes: str | None = None


def _run(fn, args: dict) -> dict:
    try:
        result = json.loads(fn(args))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if result.get("ok") is False:
        raise HTTPException(status_code=400, detail=result.get("error") or "request failed")
    try:
        render_board()
    except Exception:
        pass
    return result


@router.get("/state")
@router.get("/board")
def state() -> dict:
    return board_payload()


@router.post("/leads/draft")
def draft(body: LeadBody) -> dict:
    return _run(tools.signaldesk_draft, {"lead_id": body.lead_id})


@router.post("/leads/approve")
def approve(body: LeadBody) -> dict:
    return _run(tools.signaldesk_approve, {"lead_id": body.lead_id})


@router.post("/leads/mark")
def mark(body: LeadBody) -> dict:
    return _run(tools.signaldesk_mark, {"lead_id": body.lead_id, "stage": body.stage, "notes": body.notes})


@router.post("/leads/prepare")
def prepare(body: LeadBody) -> dict:
    return _run(tools.signaldesk_prepare_send, {"lead_id": body.lead_id})


class MapScanBody(BaseModel):
    business_type: str = Field(..., min_length=1)
    city: str | None = None
    bbox: str | None = None
    limit: int | None = 40


@router.post("/map/scan")
def map_scan(body: MapScanBody) -> dict:
    return _run(tools.signaldesk_map_scan, body.model_dump())


@router.post("/scan")
def scan() -> dict:
    return _run(tools.signaldesk_scan, {"kind": "all"})
