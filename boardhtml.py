"""Self-contained HTML pipeline board for the demo and for local review."""

from __future__ import annotations

import html
from pathlib import Path

from models import STAGES
from paths import data_root
from store import counts_by_stage, list_leads

STAGE_LABELS = {
    "new": "New",
    "qualified": "Qualified",
    "drafted": "Drafted",
    "approved": "Approved",
    "sent": "Sent",
    "replied": "Replied",
    "won": "Won",
    "lost": "Lost",
}


def _esc(val: object) -> str:
    return html.escape("" if val is None else str(val), quote=True)


def _score_class(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 35:
        return "mid"
    return "low"


def render_board(path: Path | None = None, title: str = "SignalDesk") -> Path:
    leads = list_leads(limit=400)
    counts = counts_by_stage()
    columns = []
    by_stage: dict[str, list] = {s: [] for s in STAGES}
    for lead in leads:
        by_stage.setdefault(lead.stage, []).append(lead)

    for stage in STAGES:
        cards = []
        for lead in by_stage.get(stage, []):
            remote = ""
            if lead.remote is True:
                remote = "Remote"
            elif lead.remote is False:
                remote = "Onsite"
            reasons = "".join(f"<li>{_esc(r)}</li>" for r in (lead.score_reasons or [])[:5])
            draft = ""
            if lead.draft_subject:
                draft = (
                    f"<div class='draft'><div class='draft-sub'>{_esc(lead.draft_subject)}</div>"
                    f"<pre>{_esc(lead.draft_body[:600])}</pre></div>"
                )
            contact = f"<div class='meta'>{_esc(lead.contact)}</div>" if lead.contact else ""
            loc = " · ".join(p for p in (lead.location, remote) if p)
            cards.append(
                f"<article class='card' data-id='{_esc(lead.id)}' data-stage='{_esc(lead.stage)}'>"
                f"<header><span class='co'>{_esc(lead.company)}</span>"
                f"<span class='score {_score_class(lead.score)}'>{int(lead.score)}</span></header>"
                f"<div class='sig'>{_esc(lead.signal_type)}</div>"
                f"<p class='quote'>{_esc(lead.signal_quote)}</p>"
                f"{f'<div class=\"meta\">{_esc(loc)}</div>' if loc else ''}"
                f"{f'<div class=\"meta\">{_esc(lead.role)}</div>' if lead.role else ''}"
                f"{contact}"
                f"{f'<div class=\"meta domain\">{_esc(lead.domain)}</div>' if lead.domain else ''}"
                f"{f'<ul class=\"reasons\">{reasons}</ul>' if reasons else ''}"
                f"{draft}"
                f"{f'<a class=\"src\" href=\"{_esc(lead.source_url)}\">source</a>' if lead.source_url else ''}"
                f"</article>"
            )
        columns.append(
            f"<section class='col' data-stage='{_esc(stage)}'>"
            f"<h2>{_esc(STAGE_LABELS.get(stage, stage))} <em>{int(counts.get(stage, 0))}</em></h2>"
            f"<div class='stack'>{''.join(cards) or '<p class=\"empty\">No leads</p>'}</div>"
            f"</section>"
        )

    total = sum(counts.values())
    qualified = counts.get("qualified", 0) + counts.get("drafted", 0) + counts.get("approved", 0)
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_esc(title)} — pipeline board</title>
<style>
  :root {{
    --bg: #0c1017;
    --panel: #151b24;
    --card: #1c2430;
    --line: #2a3340;
    --text: #e8eef6;
    --muted: #8b98a8;
    --accent: #6ee7b7;
    --amber: #fbbf24;
    --rose: #fb7185;
    --blue: #7dd3fc;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
    background: radial-gradient(1200px 500px at 10% -10%, #12332a 0%, transparent 50%),
                radial-gradient(900px 400px at 100% 0%, #1b2a40 0%, transparent 45%),
                var(--bg);
    color: var(--text);
  }}
  header.top {{
    padding: 22px 28px 8px; display: flex; justify-content: space-between; align-items: baseline; gap: 16px;
  }}
  header.top h1 {{
    margin: 0; font-size: 22px; letter-spacing: .04em; font-weight: 650;
  }}
  header.top h1 span {{ color: var(--accent); }}
  .sub {{ color: var(--muted); font-size: 13px; }}
  .kpis {{ display: flex; gap: 18px; font-size: 13px; color: var(--muted); }}
  .kpis strong {{ color: var(--text); font-size: 16px; margin-right: 4px; }}
  .board {{
    display: grid; grid-template-columns: repeat(8, minmax(220px, 1fr));
    gap: 12px; padding: 16px 20px 40px; overflow-x: auto;
  }}
  .col {{
    background: color-mix(in srgb, var(--panel) 92%, black);
    border: 1px solid var(--line); border-radius: 14px; min-height: 70vh;
    padding: 10px;
  }}
  .col h2 {{
    margin: 0 6px 10px; font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); display: flex; justify-content: space-between;
  }}
  .col h2 em {{ font-style: normal; color: var(--text); background: #242c38; padding: 1px 7px; border-radius: 999px; }}
  .stack {{ display: flex; flex-direction: column; gap: 8px; }}
  .card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 10px 11px;
  }}
  .card header {{ display: flex; justify-content: space-between; gap: 8px; align-items: start; }}
  .co {{ font-weight: 600; font-size: 13.5px; }}
  .score {{
    font-variant-numeric: tabular-nums; font-size: 11px; font-weight: 700;
    border-radius: 999px; padding: 1px 7px; background: #2a3340; color: var(--muted);
  }}
  .score.high {{ background: #113328; color: var(--accent); }}
  .score.mid {{ background: #3a2e10; color: var(--amber); }}
  .score.low {{ background: #3a1820; color: var(--rose); }}
  .sig {{
    display: inline-block; margin: 6px 0 4px; font-size: 10px; letter-spacing: .06em;
    text-transform: uppercase; color: var(--blue); border: 1px solid #1e3a4c;
    border-radius: 999px; padding: 0 7px;
  }}
  .quote {{ margin: 4px 0; font-size: 12px; color: #c9d4e0; line-height: 1.4; }}
  .meta {{ font-size: 11px; color: var(--muted); }}
  .reasons {{ margin: 6px 0 0; padding-left: 16px; color: var(--muted); font-size: 11px; }}
  .draft {{ margin-top: 8px; background: #12181f; border-radius: 8px; padding: 8px; }}
  .draft-sub {{ font-size: 11px; color: var(--accent); font-weight: 600; }}
  .draft pre {{
    white-space: pre-wrap; margin: 6px 0 0; font: 11px/1.4 "IBM Plex Mono", ui-monospace, monospace;
    color: #d5deea;
  }}
  a.src {{ display: inline-block; margin-top: 6px; font-size: 11px; color: var(--blue); }}
  .empty {{ color: var(--muted); font-size: 12px; padding: 8px; }}
  footer {{ padding: 0 28px 28px; color: var(--muted); font-size: 11px; }}
</style>
</head>
<body>
  <header class="top">
    <div>
      <h1><span>Signal</span>Desk</h1>
      <div class="sub">Hiring and launch signals, scored against your ICP. Draft-first — nothing sends itself.</div>
    </div>
    <div class="kpis">
      <div><strong>{total}</strong> leads</div>
      <div><strong>{qualified}</strong> in motion</div>
      <div><strong>{counts.get("approved", 0)}</strong> approved</div>
    </div>
  </header>
  <div class="board">
    {''.join(columns)}
  </div>
  <footer>Public signals only. Scores are transparent. Sending requires an in-plugin approval.</footer>
</body>
</html>
"""
    dest = path or (data_root() / "board.html")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(doc, encoding="utf-8")
    return dest
