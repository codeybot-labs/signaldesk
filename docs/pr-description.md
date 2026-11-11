# Catalog PR draft (do not open until the public repo SHA is pinned)

Title: `Add signaldesk to the plugin catalog`

This PR adds `plugin-catalog/signaldesk.yaml` only. Pin `sha` to the 40-character commit from https://github.com/codeybot-labs/signaldesk (currently a placeholder in the draft YAML under this repo at `plugin-catalog/signaldesk.yaml`).

## What it does

SignalDesk is a draft-first lead desk for founders and marketers. It scans public hiring and launch signals (HN Who is hiring, YC hiring via yc-oss, Show HN, new YC companies), scores them against a user-defined ICP with visible reasons, drafts outreach, and never sends without in-plugin approval. A `pre_tool_call` hook fail-closes send-like tools during cron/unattended runs.

Surfaces: 11 `signaldesk_*` tools, `pre_tool_call` hook, `/signaldesk` slash command, a weekday “catch-up” automation blueprint, SQLite pipeline, and a standalone HTML board. No Desktop SDK package in 0.1.0 (the HTML board is the review UI).

## Rule 13 disclosures

- Fetches public JSON from Algolia HN Search and yc-oss.github.io. Optional DNS MX (UDP only, no SMTP probing).
- Lead data stored in `$HERMES_HOME/plugin-data/signaldesk/`. No telemetry.
- No required credentials or paid providers. No third-party mail APIs. SignalDesk never transmits email; after approval it writes a local `.eml` / mailto, and the hook blocks Hermes send tools unless the lead is approved and the session is interactive.
- Drafts use the host LLM when available, otherwise a local template.

## Validation

Run at the pinned SHA:

```bash
hermes plugins validate /path/to/signaldesk --install-deps
hermes plugins doctor --ci
```

Plus `pytest` (offline fixtures) and `./demo/run_demo.sh`.

## Known issues (also in the catalog entry)

- Product Hunt / BetaList are not in 0.1.0.
- Show HN posts that live only on GitHub often have no company inbox.
- Live scans need outbound HTTPS; the demo runs fully offline from fixtures.
