#!/usr/bin/env python3
"""Build desktop/plugin.js: board.js + map.js + OpenLayers 10.5.0 (BSD-2-Clause) inline.

Desktop plugin.js may import only @hermes/plugin-sdk and react, so OpenLayers is bundled
into the file. Its JSONP loader (the only place OL builds a <script> element) is replaced
with a stub that throws: SignalDesk never uses JSONP sources, and the Desktop admission
lint refuses script injection.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts" / "desktop-src"
OL = ROOT / "assets" / "vendor" / "ol"
JSONP = 'const r=document.createElement("script")'


def main() -> int:
    ol_js = (OL / "ol.js").read_text(encoding="utf-8")
    ol_js = re.sub(r"\n//# sourceMappingURL=.*\s*$", "\n", ol_js)
    if ol_js.count(JSONP) != 1:
        raise SystemExit("unexpected ol.js build: JSONP marker not found exactly once")
    ol_js = ol_js.replace(JSONP, 'const r=(()=>{throw new Error("JSONP disabled in SignalDesk")})()')
    ol_css = (OL / "ol.css").read_text(encoding="utf-8")
    bundle = (
        "// ---- OpenLayers 10.5.0, BSD-2-Clause, (c) OpenLayers Contributors ----\n"
        "// https://github.com/openlayers/openlayers/blob/main/LICENSE.md (JSONP loader stubbed)\n"
        + ol_js.strip() + "\n"
        + "const OL_CSS = " + json.dumps(ol_css) + "\n"
        + "// ---- end OpenLayers ----\n"
    )
    board = (SRC / "board.js").read_text(encoding="utf-8")
    out = board.replace("/*__OL_BUNDLE__*/", bundle, 1).replace(
        "/*__MAP_PANEL__*/", (SRC / "map.js").read_text(encoding="utf-8"), 1)
    (ROOT / "desktop" / "plugin.js").write_text(out, encoding="utf-8")
    print(f"desktop/plugin.js: {len(out) // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
