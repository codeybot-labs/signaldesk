#!/usr/bin/env python3
"""Offline demo harness: scan fixtures, draft, approve one lead, write the board."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Environment is normally set by demo/run_demo.sh; keep the script usable alone.
os.environ.setdefault("SIGNALDESK_OFFLINE", "1")
os.environ.setdefault("SIGNALDESK_SKIP_MX", "1")
os.environ.setdefault("SIGNALDESK_FIXTURE_DIR", str(ROOT / "tests" / "fixtures"))
os.environ.setdefault("SIGNALDESK_DATA_DIR", str(ROOT / "demo" / "out" / "data"))

from icp import save_icp  # noqa: E402
from models import ICP  # noqa: E402
import toolhandlers as tools  # noqa: E402


DEMO_ICP = ICP(
    keywords=["AI", "agent", "developer tools", "infrastructure", "analytics", "cloud", "open source"],
    roles=["engineer", "devops", "growth", "founder"],
    stack=["python", "ai", "typescript"],
    locations=["San Francisco", "US", "remote"],
    remote_ok=True,
    onsite_ok=True,
    offer="an AI copilot that turns public hiring and launch signals into draft-ready outreach",
    sender_name="Alex at SignalDesk",
    booking_link="https://cal.com/example/signaldesk",
    qualify_min_score=35,
    followup_days=5,
)


def _load(s: str) -> dict:
    return json.loads(s)


def main() -> int:
    out_dir = ROOT / "demo" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_icp(DEMO_ICP)
    print("== 1. ICP saved")

    sources = _load(tools.signaldesk_sources({}))
    print("== 2. Sources")
    for row in sources.get("sources", []):
        print(f"   - {row['id']}: {'on' if row.get('enabled') else 'off'} ({row.get('message')})")

    scan = _load(tools.signaldesk_scan({"kind": "all"}))
    print("== 3. Scan", {k: scan.get(k) for k in ("ok", "inserted", "updated", "skipped", "qualified")})
    for row in scan.get("sources", []):
        print(f"   - {row['id']}: fetched={row.get('fetched')} kept={row.get('kept')}")

    listed = _load(tools.signaldesk_list({"stage": "qualified", "limit": 8}))
    leads = listed.get("leads") or []
    if not leads:
        listed = _load(tools.signaldesk_list({"limit": 8}))
        leads = listed.get("leads") or []
    if not leads:
        print("ERROR: no leads from fixtures", file=sys.stderr)
        return 1

    # Prefer hiring leads with a contact for a richer demo card.
    ranked = sorted(leads, key=lambda l: (
        0 if (l.get("contact") and l.get("signal_type") == "hiring") else 1,
        -(l.get("score") or 0),
    ))
    pick = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    print(f"== 4. Picked {pick['company']} ({pick['id']}) score={pick['score']} stage={pick['stage']}")

    drafted = _load(tools.signaldesk_draft({"lead_id": pick["id"]}))
    if not drafted.get("ok"):
        print("ERROR drafting:", drafted, file=sys.stderr)
        return 1
    print("== 5. Draft subject:", drafted["lead"]["draft_subject"])

    if second and second["id"] != pick["id"]:
        extra = _load(tools.signaldesk_draft({"lead_id": second["id"]}))
        if extra.get("ok"):
            print(f"== 5b. Also drafted {extra['lead']['company']} (leave unapproved for the video Approve click)")

    approved = _load(tools.signaldesk_approve({"lead_id": pick["id"]}))
    if not approved.get("ok"):
        print("ERROR approving:", approved, file=sys.stderr)
        return 1
    print("== 6. Approved:", approved["lead"]["company"])

    prepared = _load(tools.signaldesk_prepare_send({"lead_id": pick["id"]}))
    print("== 7. Prepare send sent=false eml=", prepared.get("eml_path"))

    board_path = out_dir / "board.html"
    board = _load(tools.signaldesk_board({"path": str(board_path)}))
    print("== 8. Board:", board.get("path"))
    (out_dir / "summary.json").write_text(
        json.dumps(
            {
                "scan": {k: scan.get(k) for k in ("ok", "inserted", "updated", "skipped", "qualified", "counts")},
                "picked": {
                    "id": pick["id"],
                    "company": pick["company"],
                    "score": pick["score"],
                    "signal_type": pick["signal_type"],
                },
                "board": board.get("path"),
                "eml": prepared.get("eml_path"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("Done. Open the board with:")
    print("  python3 demo/serve_demo.py")
    print("  then visit http://127.0.0.1:8765/board.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
