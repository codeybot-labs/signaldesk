from hooks import make_pre_tool_call
from icp import save_icp
from models import ICP
from pipeline import scan
from store import list_leads, save_lead


class _Cron:
    def current_cron_execution(self):
        return object()


class _Interactive:
    def current_cron_execution(self):
        return None


def test_hook_blocks_send_in_cron():
    hook = make_pre_tool_call(_Cron())
    result = hook("send_email", {"to": "jobs@example.com"}, task_id="t1")
    assert result is not None
    assert result["action"] == "block"
    assert "cron" in result["message"].lower() or "unattended" in result["message"].lower()


def test_hook_blocks_unapproved_interactive_send():
    hook = make_pre_tool_call(_Interactive())
    result = hook("send_email", {"to": "nobody@example.com"}, task_id="t1")
    assert result is not None
    assert result["action"] == "block"


def test_hook_allows_approved_interactive_send():
    save_icp(ICP(keywords=["analytics"], roles=["devops"], remote_ok=True, qualify_min_score=10))
    scan(kind="hn_hiring")
    lead = next(l for l in list_leads(limit=200) if l.company == "Simple Analytics")
    lead.stage = "approved"
    lead.draft_body = "hello"
    lead.draft_subject = "hi"
    save_lead(lead)
    hook = make_pre_tool_call(_Interactive())
    # Should not block when the recipient matches an approved lead
    result = hook("send_email", {"to": lead.contact or f"hello@{lead.domain}"}, task_id="t1")
    assert result is None
    # Harmless tools are never blocked
    assert hook("signaldesk_list", {}, task_id="t1") is None
    assert hook("signaldesk_prepare_send", {"lead_id": lead.id}, task_id="t1") is None
