import json
from pathlib import Path

from icp import save_icp, update_icp
from models import ICP
from pipeline import scan
from store import counts_by_stage, get_lead, list_leads
import toolhandlers as tools


def _icp():
    return save_icp(ICP(
        keywords=["AI", "agent", "developer", "infrastructure", "analytics", "cloud"],
        roles=["engineer", "devops", "growth"],
        stack=["python", "ai"],
        locations=["San Francisco", "US", "remote"],
        remote_ok=True,
        onsite_ok=True,
        offer="an AI copilot for B2B sales teams",
        sender_name="Alex at SignalDesk",
        booking_link="https://cal.com/example/signaldesk",
        qualify_min_score=35,
    ))


def test_offline_scan_inserts_leads_from_fixtures():
    _icp()
    report = scan(kind="all")
    assert report["ok"] is True
    assert report["inserted"] >= 20
    assert not report["errors"]
    ids = {row["id"] for row in report["sources"]}
    assert {"hn_hiring", "yc_hiring", "hn_show", "yc_launches"} <= ids
    leads = list_leads(limit=200)
    assert any(l.signal_type == "hiring" for l in leads)
    assert any(l.signal_type == "launch" for l in leads)
    # HN hiring fixture includes Simple Analytics
    assert any(l.company == "Simple Analytics" for l in leads)
    # YC launches fixture includes Ample Computer
    assert any("Ample" in l.company for l in leads)


def test_dedup_by_domain_on_second_scan():
    _icp()
    first = scan(kind="hn_hiring")
    second = scan(kind="hn_hiring")
    assert first["inserted"] > 0
    assert second["inserted"] == 0
    assert second["updated"] >= first["inserted"]


def test_draft_approve_prepare_send_and_board(tmp_path):
    _icp()
    scan(kind="hn_hiring")
    leads = list_leads(stage="qualified", limit=10)
    assert leads, "expected qualified leads from the ICP + fixtures"
    lead = leads[0]
    drafted = json.loads(tools.signaldesk_draft({"lead_id": lead.id}))
    assert drafted["ok"] is True
    assert drafted["lead"]["draft_body"]
    assert drafted["method"] == "template"  # no host LLM in tests
    approved = json.loads(tools.signaldesk_approve({"lead_id": lead.id}))
    assert approved["ok"] is True
    assert approved["lead"]["stage"] == "approved"
    prepared = json.loads(tools.signaldesk_prepare_send({"lead_id": lead.id}))
    assert prepared["ok"] is True
    assert prepared["sent"] is False
    assert Path(prepared["eml_path"]).is_file()
    board_path = tmp_path / "board.html"
    board = json.loads(tools.signaldesk_board({"path": str(board_path)}))
    assert board["ok"] is True
    html = Path(board["path"]).read_text(encoding="utf-8")
    assert "SignalDesk" in html
    assert lead.company in html


def test_prepare_send_refuses_unapproved():
    _icp()
    scan(kind="hn_show")
    lead = list_leads(limit=1)[0]
    result = json.loads(tools.signaldesk_prepare_send({"lead_id": lead.id}))
    assert result["ok"] is False
