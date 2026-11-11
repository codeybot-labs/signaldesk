# SignalDesk demo script (~75 seconds)

Voiceover plus on-screen action for a recording under 90 seconds. Record the **interactive** board so Approve is a real click.

**Prep (not in the video):**

```bash
cd /workspace/signaldesk   # or your checkout of github.com/codeybot-labs/signaldesk
./demo/run_demo.sh
python3 demo/serve_demo.py
```

Leave that process running. The board is:

**http://127.0.0.1:8765/board.html**

Record at **1920×1080** if you can (all eight columns fit). **1280×800** also works; you will scroll the board sideways a little. Use ffmpeg or Playwright against that URL. Do not send a real email on camera.

The harness drafts two leads and approves one. After a fresh `./demo/run_demo.sh` you should see a card already in **Approved** and another in **Drafted**.

Target length: **about 70–75 seconds**. Leave a little head and tail for title cards.

---

### 0:00–0:08 — Hook
**VO:** “SignalDesk watches public hiring posts and launches, and turns the ones that match your ICP into drafts you actually approve.”
**Visual:** Full board at http://127.0.0.1:8765/board.html. Hold on the header: the offer line, keyword chips, and the green **no key** badges on HN and YC.

### 0:08–0:20 — Sources and pipeline
**VO:** “It reads Who is hiring on Hacker News, YC companies that are hiring, Show HN, and new YC companies. No paid data vendor. Everything lands on this board, scored, in the usual pipeline.”
**Visual:** Slow pan across the columns — New, Qualified, Drafted, Approved. Hover a high-score Qualified card so the quote and score are readable.

### 0:20–0:34 — Open a drafted card
**VO:** “When something looks right, you get a short draft from the actual post — not a generic blurb. Here's one that's already drafted, waiting on you.”
**Visual:** Click the card in the **Drafted** column. The side panel opens: company, score, the public signal, “why this score,” and the draft. If the card isn't obvious, type part of the company name in **Filter companies…** first.

### 0:34–0:50 — Approve, still not sent
**VO:** “Read the reasons, read the draft, then hit Approve. That's the in-plugin gate. Until you do this, nothing goes out — not even from a cron job.”
**Visual:** Click **Approve**. The card should move to **Approved**. Optionally click **Copy** or **Open .eml** to show the local file, then come back to the board. Do not open a real mailbox send dialog if you can avoid it.

### 0:50–0:63 — Fail-closed sending
**VO:** “If you do want to mail it, SignalDesk writes a local email file. Unattended jobs can scan and summarize overnight, but they are blocked from sending.”
**Visual:** Linger on the Approved panel footer: Approve is gone, Copy and Open .eml remain, plus the line that nothing sends itself.

### 0:63–0:75 — Close
**VO:** “Install SignalDesk from the Hermes catalog, set your ICP, and start from public signals — not a mystery list.”
**Visual:** Close the panel (Escape or the ×), pull back to the full board. End card: **SignalDesk** — github.com/codeybot-labs/signaldesk, and a tag for @NousResearch.

---

### Recording notes

- Exact URL: `http://127.0.0.1:8765/board.html` after `python3 demo/serve_demo.py`.
- Click path: land on the board → pan columns → click the **Drafted** card → read the panel → click **Approve** → (optional) **Open .eml** → close panel → wide shot.
- If a voiceover pass runs long, trim the “paid data vendor” clause first; keep the Approve beat.
- Suggested titles: “Public signals in” / “Scored against your ICP” / “Draft-first. You approve.”
