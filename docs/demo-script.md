# SignalDesk demo script (~75 seconds)

Voiceover + on-screen action for a <90s recording. Record against the offline board so the take is reproducible.

**Prep (not in the video):**

```bash
./demo/run_demo.sh
python3 -m http.server 8765 --directory demo/out
```

Open `http://127.0.0.1:8765/board.html` at a wide desktop size (1440×900 or similar). Have a terminal ready with the same command visible if you want a 3-second “it ran offline” establishing shot. Screen-record the board (Playwright or ffmpeg); the voiceover can be laid on later.

Target length: **about 75 seconds**. Leave a little head and tail for title/end cards.

---

### 0:00–0:07 — Hook
**VO:** “SignalDesk watches public hiring and launch posts, and turns the ones that match your ICP into drafts you actually approve.”
**Visual:** Full pipeline board. Slowly pan from left (New / Qualified) toward the middle columns.

### 0:07–0:18 — Sources
**VO:** “It scans Who is hiring on Hacker News, YC companies that are hiring, fresh Show HN launches, and new YC companies — all keyless public feeds. No paid data vendor.”
**Visual:** Hold on hiring cards (quote, role, location) then cut or scroll to a launch card so both signal types are obvious.

### 0:18–0:30 — Scoring
**VO:** “Every lead gets a transparent score: keywords, role, location, remote, exclusions, even whether the domain publishes mail records. You can see why it ranked.”
**Visual:** Zoom a high-score Qualified card so the numeric score and the reason list are readable.

### 0:30–0:48 — Draft, then approve
**VO:** “When a company looks right, SignalDesk writes a short draft from the actual quote — not a generic template dump. You review it, then approve it in the plugin. Until you do, nothing goes out.”
**Visual:** Cut to an Approved column card with the draft subject and body visible. If you recorded the demo run, flash the terminal lines “Draft subject…” and “Approved…” for a second before returning to the board.

### 0:48–0:63 — Fail-closed sending
**VO:** “Sending is a separate step: a local email file or your own mail tool. Cron can scan and summarize overnight, but unattended jobs are blocked from sending. Draft first, always.”
**Visual:** Linger on the Approved card and the footer line “Sending requires an in-plugin approval.” Optional: show the `.eml` path from the demo output, not an inbox send.

### 0:63–0:75 — Close
**VO:** “Install SignalDesk from the Hermes plugin catalog, set your ICP, and start from real public signals — not a mystery list.”
**Visual:** Pull back to the full board. End card: **SignalDesk** — `github.com/codeybot-labs/signaldesk` and a tag for @NousResearch.

---

### Recording notes

- Do not send a real email on camera.
- The offline harness always approves one lead and rewrites `demo/out/board.html`, so retakes stay consistent.
- If a voiceover pass runs long, drop the MX/reasons clause in the scoring beat first; keep the approve-and-fail-closed beat intact.
- Suggested on-screen titles: “Public signals in” / “Scored against your ICP” / “Draft-first. You approve.”
