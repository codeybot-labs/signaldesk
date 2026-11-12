import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import toolhandlers as tools
from hooks import make_pre_tool_call
from icp import save_icp
from models import ICP
from pipeline import scan
from sources.producthunt import ProductHuntSource, _token
from store import get_lead, list_leads, save_lead


def _plugin():
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("signaldesk_plugin", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _drafted_lead():
    save_icp(ICP(keywords=["analytics"], roles=["devops"], remote_ok=True, qualify_min_score=10))
    scan(kind="hn_hiring")
    lead = next(l for l in list_leads(limit=200) if l.company == "Simple Analytics")
    drafted = json.loads(tools.signaldesk_draft({"lead_id": lead.id}))
    assert drafted["ok"] is True
    return get_lead(lead.id)


def test_mark_refuses_approved_stage():
    lead = _drafted_lead()
    result = json.loads(tools.signaldesk_mark({"lead_id": lead.id, "stage": "approved"}))
    assert result["ok"] is False
    assert "user-only" in result["error"].lower()
    assert get_lead(lead.id).stage == "drafted"


class _Interactive:
    def current_cron_execution(self):
        return None


def test_mark_refuses_sent_from_drafted():
    lead = _drafted_lead()
    result = json.loads(tools.signaldesk_mark({"lead_id": lead.id, "stage": "sent"}))
    assert result["ok"] is False
    assert "user-only" in result["error"].lower()
    fresh = get_lead(lead.id)
    assert fresh.stage == "drafted"
    assert not fresh.sent_at
    # The send gate must still treat this lead as unapproved after the refusal.
    hook = make_pre_tool_call(_Interactive())
    send = hook("send_email", {"to": fresh.contact or f"hello@{fresh.domain}"}, task_id="t1")
    assert send is not None
    assert send["action"] == "block"


def test_mark_refuses_sendable_jumps_from_drafted():
    lead = _drafted_lead()
    for stage in ("replied", "won"):
        result = json.loads(tools.signaldesk_mark({"lead_id": lead.id, "stage": stage}))
        assert result["ok"] is False, stage
        assert "user-only" in result["error"].lower()
        assert get_lead(lead.id).stage == "drafted"


def test_mark_sendable_transitions_follow_the_real_flow():
    lead = _drafted_lead()
    lead.stage = "approved"
    save_lead(lead)
    assert json.loads(tools.signaldesk_mark({"lead_id": lead.id, "stage": "sent"}))["ok"] is True
    assert json.loads(tools.signaldesk_mark({"lead_id": lead.id, "stage": "replied"}))["ok"] is True
    assert json.loads(tools.signaldesk_mark({"lead_id": lead.id, "stage": "won"}))["ok"] is True
    assert get_lead(lead.id).stage == "won"


def test_slash_approve_and_handler_still_work():
    lead = _drafted_lead()
    plugin = _plugin()
    assert "Usage:" in plugin._slash_signaldesk("approve")
    text = plugin._slash_signaldesk(f"approve {lead.id}")
    assert "Approved" in text
    assert get_lead(lead.id).stage == "approved"


def test_approve_is_not_a_model_tool():
    class Ctx:
        def __init__(self):
            self.tools = []

        def register_tool(self, name, **kwargs):
            self.tools.append(name)

        def register_hook(self, *args, **kwargs):
            pass

        def register_command(self, *args, **kwargs):
            pass

        def register_automation_blueprint(self, *args, **kwargs):
            pass

    ctx = Ctx()
    _plugin().register(ctx)
    assert "signaldesk_approve" not in ctx.tools
    assert "signaldesk_draft" in ctx.tools
    assert "signaldesk_mark" in ctx.tools


def test_producthunt_ignores_environ(monkeypatch):
    monkeypatch.setenv("PRODUCTHUNT_TOKEN", "env-token-should-be-ignored")
    assert _token() == ""
    ok, _msg = ProductHuntSource().available()
    assert ok is False


def test_producthunt_reads_secret_scope(monkeypatch):
    fake_agent = types.ModuleType("agent")
    fake_scope = types.ModuleType("agent.secret_scope")
    fake_scope.get_secret = lambda name: "from-scope" if name == "PRODUCTHUNT_TOKEN" else ""
    monkeypatch.setitem(sys.modules, "agent", fake_agent)
    monkeypatch.setitem(sys.modules, "agent.secret_scope", fake_scope)
    import sources.producthunt as ph
    importlib.reload(ph)
    try:
        assert ph._token() == "from-scope"
        ok, _msg = ph.ProductHuntSource().available()
        assert ok is True
    finally:
        monkeypatch.delitem(sys.modules, "agent.secret_scope", raising=False)
        monkeypatch.delitem(sys.modules, "agent", raising=False)
        importlib.reload(ph)
