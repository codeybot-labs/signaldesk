Adds `plugin-catalog/signaldesk.yaml`, pinned to the SignalDesk v0.2.0 commit named in the catalog entry. Hackathon entry.

## What it does

SignalDesk is a draft-first lead desk for founders and marketers. It scans public hiring and launch signals (HN "Who is hiring?", YC companies hiring via yc-oss, Show HN, Launch HN, newly added YC companies, and optionally Product Hunt with the user's own token) and, with the **LocalLead Map**, local businesses from OpenStreetMap for a city + business type or a drawn area, shown as pins on an OpenLayers map next to a table. All of them feed one pipeline: it scores each lead against a user-defined ICP with visible reasons (for map leads: business type, website, email, phone), dedupes by domain, keeps a persistent pipeline (new → qualified → drafted → approved → sent → replied/won/lost), drafts outreach that quotes the signal, and tracks follow-ups. It never sends anything without approval inside the plugin.

## Hermes surfaces

- 12 `signaldesk_*` tools (ICP, scan, map_scan, list, draft, approve, mark, follow-ups, CSV export, sources, prepare_send, board)
- `pre_tool_call` hook: blocks send-like tools for a SignalDesk lead unless that draft is approved; fails closed during cron/unattended runs
- `/signaldesk` slash command
- Weekday catch-up automation blueprint (scan + summarize only, never sends)
- Hermes Desktop page (`desktop/plugin.js` + `dashboard/plugin_api.py`, imports only the SDK + react; OpenLayers 10.5.0 is bundled inline with its JSONP loader stubbed) and an interactive local HTML board with Pipeline and Map views

## Rule 13 disclosures

- Network: public JSON from Algolia HN Search (`hn.algolia.com`) and the yc-oss static API (`yc-oss.github.io`); optional DNS MX lookups (no SMTP probing); optional Product Hunt GraphQL v2 only when `PRODUCTHUNT_TOKEN` is set (optional, read via `secret_scope`; Product Hunt API terms restrict commercial use without their permission).
- OpenStreetMap (only when the user runs a map scan): Nominatim geocoding at most 1 request/second with an identifying User-Agent (`SignalDesk-Hermes-plugin/0.2.0 (+https://github.com/codeybot-labs/signaldesk)`), cached 30 days; Overpass API one request at a time with a server timeout and result cap, cached 7 days; standard OSM tiles loaded by the browser while the map is open. Offline or on failure it falls back to a small bundled real OSM extract (`geodata/`, Zürich dentists and cafés).
- Licensing: map data © OpenStreetMap contributors, ODbL 1.0. Attribution is shown on the map, the table and the lead panel, and written into CSV rows (plus a footer row) and an `X-SignalDesk-Data-Attribution` header in `.eml` files. Bundled OpenLayers 10.5.0 is BSD-2-Clause (NOTICE included).
- Filesystem: lead data in `$HERMES_HOME/plugin-data/signaldesk/`; approved drafts written there as local `.eml` files.
- No shell commands, no background processes beyond the opt-in automation blueprint, no stored credentials, no telemetry, no third-party mail APIs, no paid data providers.
- SignalDesk never transmits email itself.

## Validation

`hermes plugins validate --install-deps` passes on a fresh clone at the pinned SHA (security scan safe, desktop surface clean, capabilities match: 12 tools, 1 hook). `hermes plugins doctor --ci` passes. 30 pytest tests run offline (fixtures plus a mocked Nominatim/Overpass covering the rate limit, caching, demo fallback and export attribution).

## Known issues

- The Desktop page passes desktop-surface validation but wasn't clicked through in a live Desktop window on the build machine; the HTML board is the reviewed UI.
- Show HN posts hosted only on GitHub often have no company inbox.
- Live scans need outbound HTTPS to Algolia and yc-oss.github.io; each source is capped.
- Public Overpass instances can be slow or unreachable. overpass-api.de was unreachable from the build machine, so the live map test and the demo video used the Swiss instance `overpass.osm.ch` via `SIGNALDESK_OVERPASS_URL`. The Desktop Map tab was smoke-tested in a browser harness with a stubbed SDK, not in a live Desktop window.
