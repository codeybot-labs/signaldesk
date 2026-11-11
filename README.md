# SignalDesk

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that turns **public hiring and launch signals** into a scored, draft-first outreach queue.

Install it, describe your ICP, scan, review the board, approve one lead. **Nothing is sent unless you approve it in an interactive session.** Cron jobs and unattended runs fail closed.

This is a plugin, not a skill: it ships tools, a `pre_tool_call` send guard, a slash command, an automation blueprint, a SQLite pipeline, and a standalone HTML board.

## Why this exists

Founders and marketers already watch “Ask HN: Who is hiring?”, Show HN, and the YC directory. Doing that by hand every week is slow, and most “AI SDR” tools want a paid data vendor and then email people on their own.

SignalDesk stays on **keyless public sources**, scores each company against *your* ICP with visible reasons, and writes a draft you can edit. Sending is a separate, explicit step.

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

## Quick start

```
Set my SignalDesk ICP: I sell an AI copilot for B2B sales teams.
Keywords: AI, agents, developer tools, infrastructure. Remote is fine.
Then scan hiring and launch sources and show me the top qualified leads.
```

Or from a terminal, with no network, using the bundled fixtures:

```bash
./demo/run_demo.sh
python3 -m http.server 8765 --directory demo/out
# open http://127.0.0.1:8765/board.html
```

Slash command: `/signaldesk status`, `/signaldesk scan`, `/signaldesk board`.

## What it does

1. **Scan** public feeds (hiring, launches, or both).
2. **Normalize** company, domain, role, location, a short quote, and a source URL.
3. **Score** against your ICP (keywords, roles, stack, locations, remote/onsite, stage, exclusions, public contact, MX). Every point has a reason.
4. **Dedup** by company domain (or source id when there is no domain).
5. **Draft** a short email. Never sends it.
6. **Approve** in-plugin. Only then can you export a local `.eml` / `mailto:` or use a Hermes email tool.
7. **Follow-ups** lists `sent` leads older than `followup_days`.
8. **Board / CSV** for review and export.

Pipeline stages: `new → qualified → drafted → approved → sent → replied / won / lost`.

## Sources (v0.1)

| id | Signal | Source | Key? |
|---|---|---|---|
| `hn_hiring` | Hiring | Official HN “Who is hiring?” thread via [Algolia HN Search](https://hn.algolia.com/api) | No |
| `yc_hiring` | Hiring | [yc-oss](https://yc-oss.github.io/) `companies/hiring.json` | No |
| `hn_show` | Launch | Recent Show HN posts via Algolia | No |
| `yc_launches` | Launch | yc-oss `companies/changes/latest.json` (`added` only) | No |

`signaldesk_sources` reports enablement and rate-limit notes. The registry is pluggable; Product Hunt / BetaList are **not** in 0.1.0.

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
| `signaldesk_sources` | List sources |
| `signaldesk_board` | Regenerate the HTML board |

## Draft-first and the send guard

- Tools never transmit email. `signaldesk_prepare_send` writes a file and returns copy/mailto text.
- A `pre_tool_call` hook blocks send-like tools (`send_email`, SMTP, Gmail, etc.) unless a matching lead is `approved` (or later) **and** the session is interactive.
- If `ctx.current_cron_execution()` is set, sends are blocked even for approved leads. The bundled automation blueprint only scans and summarizes.

## Disclosures (catalog rule 13)

- **Network:** HTTPS GET to Algolia HN Search and `yc-oss.github.io`. Optional DNS MX lookups over UDP (no SMTP banner or RCPT probing). No third-party mail APIs. No telemetry.
- **Data:** Leads and ICP live in `$HERMES_HOME/plugin-data/signaldesk/` (override with `SIGNALDESK_DATA_DIR`). Nothing in this repo is a credential store.
- **Credentials:** None required. Future optional sources that need a token would use Hermes `secret_scope`; none ship in 0.1.0.
- **LLM:** Drafts call `ctx.llm` when the host provides it, otherwise a template. No plugin-side model signup.
- **Sending:** SignalDesk does not send mail. After approval you open the `.eml`, use the mailto link, or a Hermes email tool, which the hook still gates.
- **Sources:** Public comments and public directory snapshots only. We do not harvest commit emails, scrape the YC site HTML, or republish the yc-oss corpus. Attribute HN, YC, and yc-oss when you share derived lists.
- **Offline / fixtures:** Tests and `demo/run_demo.sh` read `tests/fixtures/` when `SIGNALDESK_OFFLINE=1`. Live scans need outbound HTTPS.

## Cron blueprint

“SignalDesk catch-up” (`weekdays 09:00` by default) scans and summarizes new qualified leads. It is written so the model must not send mail; the hook enforces that.

## Development

```bash
# tests (offline, no DNS)
SIGNALDESK_OFFLINE=1 SIGNALDESK_SKIP_MX=1 python -m pytest -q

# official catalog checks
hermes plugins validate . --install-deps
hermes plugins doctor --ci
```

Python 3.10+, stdlib only (urllib + sqlite3 + a tiny DNS MX client).

## License

MIT. See [LICENSE](LICENSE).
