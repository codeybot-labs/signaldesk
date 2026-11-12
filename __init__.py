"""SignalDesk — public hiring and launch signals, scored and drafted, never sent alone."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Hermes may import this file without putting the plugin directory on sys.path.
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import schemas
import toolhandlers as tools
from hooks import make_pre_tool_call
from icp import load_icp
from store import counts_by_stage

logger = logging.getLogger(__name__)

_BLUEPRINT_PROMPT = """You are running a SignalDesk catch-up. Do not send any outreach.

1. Call signaldesk_sources to see which feeds are enabled.
2. Call signaldesk_scan with kind=all.
3. Call signaldesk_list with stage=qualified and a short limit (10).
4. Summarize the top 5 new or qualified leads: company, signal, score, and why it matched the ICP.
5. If the user has an offer configured, mention that drafts can be written with signaldesk_draft, but do not draft everything automatically.
6. Remind the user that nothing is sent until they approve a lead on the board, in Desktop, or with /signaldesk approve <id>.
If a tool errors, report it and stop — do not retry sends, and never call email or SMTP tools.
"""


def _slash_signaldesk(raw_args: str) -> str:
    raw = (raw_args or "").strip()
    parts = raw.split(None, 1)
    verb = (parts[0] if parts else "").lower()
    rest = parts[1].strip() if len(parts) > 1 else ""
    if verb in {"", "status", "help"}:
        try:
            icp = load_icp()
            counts = counts_by_stage()
            total = sum(counts.values())
            offer = icp.offer or "(no offer set — call signaldesk_set_icp)"
            lines = [
                "SignalDesk — draft-first lead desk",
                f"Leads: {total}  " + "  ".join(f"{k}={v}" for k, v in counts.items() if v),
                f"ICP offer: {offer}",
                "Commands: /signaldesk status | scan | board | approve <id>",
                "Nothing is sent until you approve a lead on the board, in Desktop, or with /signaldesk approve <id>.",
            ]
            return "\n".join(lines)
        except Exception as exc:
            return f"SignalDesk status failed: {exc}"
    if verb == "scan":
        result = tools.signaldesk_scan({"kind": "all"})
        try:
            data = json.loads(result)
            return (
                f"Scan complete: inserted={data.get('inserted', 0)} "
                f"updated={data.get('updated', 0)} errors={len(data.get('errors') or [])}. "
                "Use signaldesk_list to review. Nothing was sent."
            )
        except Exception:
            return result
    if verb == "board":
        result = tools.signaldesk_board({})
        try:
            data = json.loads(result)
            return f"Board written to {data.get('path')}"
        except Exception:
            return result
    if verb == "approve":
        if not rest:
            return "Usage: /signaldesk approve <lead_id>"
        result = tools.signaldesk_approve({"lead_id": rest})
        try:
            data = json.loads(result)
            if data.get("ok"):
                lead = data.get("lead") or {}
                return f"Approved {lead.get('company') or rest}. Nothing was sent."
            return data.get("error") or result
        except Exception:
            return result
    return "Usage: /signaldesk [status|scan|board|approve <id>]"


def register(ctx):
    tools.set_context(ctx)
    toolset = "signaldesk"
    for schema in schemas.ALL_SCHEMAS:
        name = schema["name"]
        handler = tools.HANDLERS[name]
        ctx.register_tool(name=name, toolset=toolset, schema=schema, handler=handler)

    ctx.register_hook("pre_tool_call", make_pre_tool_call(ctx))

    ctx.register_command(
        "signaldesk",
        handler=_slash_signaldesk,
        description="SignalDesk status, scan, board, or approve a lead",
        args_hint="[status|scan|board|approve <id>]",
    )

    try:
        ctx.register_automation_blueprint(
            "catchup",
            title="SignalDesk catch-up",
            description=(
                "Scan public hiring and launch signals, score them against your ICP, "
                "and summarize new qualified leads. Never sends outreach."
            ),
            schedule_template="0 9 * * 1-5",
            prompt_template=_BLUEPRINT_PROMPT,
            category="sales",
            tags=("leads", "hiring", "draft-first"),
        )
    except Exception as exc:
        logger.warning("SignalDesk automation blueprint not registered: %s", exc)
