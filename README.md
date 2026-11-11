# SignalDesk

<p align="center">
  <img src="assets/catalog-banner.png" alt="SignalDesk — public hiring and launch signals, scored against your ICP. Draft-first — nothing sends itself." width="100%">
</p>

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that turns **public hiring and launch signals** into a scored, draft-first outreach queue.

Install it, describe your ICP, scan, review the board, approve one lead. **Nothing is sent unless you approve it in an interactive session.** Cron jobs and unattended runs fail closed.

<p align="center">
  <img src="docs/screenshots/01-board-1920.png" alt="SignalDesk pipeline board at 1920×1080, with columns from New through Lost and ICP plus no-key source badges in the header." width="100%">
</p>

<p align="center">
  <img src="docs/screenshots/04-draft-approve.png" alt="Side panel on a drafted lead showing score reasons, the public signal, the draft, and Approve / Copy / Open .eml buttons." width="100%">
</p>

## Why this beats a skill

A skill can remind the model to “go look at Who is hiring and write some emails.” It cannot keep a pipeline, it cannot stop a cron job from sending, and it will not still work when the model forgets the policy.

SignalDesk is a plugin, not a prompt:

- **Tools** for ICP, scan, list, draft, approve, mark, follow-ups, CSV, sources, a local `.eml`, and the HTML board
- A **`pre_tool_call` hook** that blocks send-like tools unless the lead is approved *and* the session is interactive
- A **slash command** (`/signaldesk`) and a weekday **catch-up blueprint** that only scans and summarizes
- A **SQLite pipeline** with domain dedup and transparent scores
- An **interactive HTML board** (what the demo records) and a **Hermes Desktop page** (`desktop/plugin.js`) that talks to the same backend

## Install

```bash
hermes plugins install codeybot-labs/signaldesk
hermes plugins enable signaldesk
```

After it is listed in the official catalog:

```bash
hermes plugins install signaldesk
```

Requires Hermes `>= 0.22.0`. No paid APIs and no plugin-side model key. Drafts use the host LLM when Hermes provides `ctx.llm`, and a local template otherwise.

Optional Desktop: enable the plugin, then **Capabilities → Plugins → Rescan** so the SignalDesk sidebar page can load. The Desktop half was validated (`desktop surface` passed) but not clicked through in a live Desktop window on the build machine.

## Quick start

Example prompts:

```
Set my SignalDesk ICP: I sell an AI copilot for B2B sales teams.
Keywords: AI, agents, developer tools, infrastructure. Remote is fine.
Then scan hiring and launch sources and show me the top qualified leads.
```

```
Draft the top qualified SignalDesk lead, show me the score reasons,
and wait — don't approve until I've read the draft.
```

```
/signaldesk status
```

Offline, with bundled fixtures (no network):

```bash
./demo/run_demo.sh
python3 demo/serve_demo.py
# open http://127.0.0.1:8765/board.html
```

Click a card for score reasons, the public quote, and the draft. **Approve**, **Copy**, and **Open .eml** call local handlers. Nothing is emailed.

## Sources (v0.1)

| id | Signal | Source | Key? |
|---|---|---|---|
| `hn_hiring` | Hiring | Official HN “Who is hiring?” thread via [Algolia HN Search](https://hn.algolia.com/api) | No |
| `yc_hiring` | Hiring | [yc-oss](https://yc-oss.github.io/) `api/companies/hiring.json` | No |
| `hn_show` | Launch | Recent Show HN posts via Algolia | No |
| `yc_launches` | Launch | yc-oss `api/changes/latest.json` (`added` only) | No |
| `producthunt` | Launch | Official Product Hunt GraphQL v2 | Optional `PRODUCTHUNT_TOKEN` |

`signaldesk_sources` reports enablement and rate-limit notes. Product Hunt stays **off** until you set the token through Hermes `secret_scope` or the environment. **Product Hunt API terms restrict commercial use** without permission — only enable that source if your use is allowed.

BetaList is **not** shipped. Their site terms limit copying and commercial or public reuse of their materials, and API access is case-by-case, so a keyless RSS source would not be a clean fit.

A live scan (11 Nov 2026, Asia/Calcutta) reached current Algolia HN threads, the yc-oss hiring snapshot (~1498 companies), Show HN, and the changes feed (2 new companies that day). Each scan caps how many records it keeps per source so a 1,498-company hiring dump does not flood the board.

## Safety model

- **Draft-first.** Tools write drafts only. `signaldesk_approve` is the in-plugin gate and still does not send.
- **Sending is a separate, explicit step.** `signaldesk_prepare_send` writes a local `.eml` and a `mailto:` link. There is no third-party mail API.
- **`pre_tool_call` gate.** Send-like tools (`send_email`, SMTP, Gmail, …) are blocked unless a matching lead is already approved (or later) **and** the session is interactive.
- **Cron fail-closed.** If `ctx.current_cron_execution()` is set, sends are blocked even for approved leads. The catch-up blueprint only scans and summarizes.
- **Public signals only.** No commit-email harvesting, no SMTP probing (MX is DNS UDP only), no scraping the YC HTML site.

## Tools

| Tool | Purpose |
|---|---|
| `signaldesk_set_icp` | Save ICP (keywords, offer, booking link, thresholds) |
| `signaldesk_scan` | Fetch, score, upsert |
| `signaldesk_list` | Filter by stage or signal type |
| `signaldesk_draft` | Write a draft, move to `drafted` |
| `signaldesk_approve` | In-plugin approval gate — still does not send |
| `signaldesk_prepare_send` | Write a local `.eml` + mailto for an **approved** lead |
| `signaldesk_mark` | `sent` / `replied` / `won` / `lost` |
| `signaldesk_followups` | Due follow-ups |
| `signaldesk_export_csv` | CSV under the plugin data dir |
| `signaldesk_sources` | List sources, including optional ones that are off |
| `signaldesk_board` | Regenerate the HTML board |

Stages: `new → qualified → drafted → approved → sent → replied / won / lost`.

## Disclosures (catalog rule 13)

- **Network:** HTTPS GET to Algolia HN Search and `yc-oss.github.io`. Optional DNS MX lookups over UDP (no SMTP banner or RCPT probing). Optional HTTPS POST to Product Hunt GraphQL v2 only when `PRODUCTHUNT_TOKEN` is set. No third-party mail APIs. No telemetry.
- **Data:** Leads and ICP live in `$HERMES_HOME/plugin-data/signaldesk/` (override with `SIGNALDESK_DATA_DIR`). Nothing in this repo is a credential store.
- **Credentials:** None required for the core sources. The optional Product Hunt token is `optional_env` / `secret_scope` (`PRODUCTHUNT_TOKEN`), never required to install or scan the keyless feeds.
- **LLM:** Drafts call `ctx.llm` when the host provides it, otherwise a template. No plugin-side model signup.
- **Sending:** SignalDesk does not send mail. After approval you open the `.eml`, use the mailto link, or a Hermes email tool, which the hook still gates.
- **Sources:** Public comments and public directory snapshots only. We do not republish the yc-oss corpus. Attribute HN, YC, yc-oss, and (if enabled) Product Hunt when you share derived lists.
- **Offline / fixtures:** Tests and `demo/run_demo.sh` read `tests/fixtures/` when `SIGNALDESK_OFFLINE=1`. Live scans need outbound HTTPS.

## Development

```bash
SIGNALDESK_OFFLINE=1 SIGNALDESK_SKIP_MX=1 python -m pytest -q
hermes plugins validate . --install-deps
hermes plugins doctor --ci
```

Python 3.10+, stdlib only for the plugin core (urllib + sqlite3 + a tiny DNS MX client). The optional Desktop/dashboard backend uses FastAPI, which Hermes already provides.

## License

MIT. See [LICENSE](LICENSE).
