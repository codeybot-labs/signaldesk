#!/usr/bin/env python3
"""Local demo server: interactive board + tiny API that calls SignalDesk handlers.

    python3 demo/serve_demo.py
    # then open http://127.0.0.1:8765/board.html

This is the page to screen-record. It does not send email.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("SIGNALDESK_OFFLINE", "1")
os.environ.setdefault("SIGNALDESK_SKIP_MX", "1")
os.environ.setdefault("SIGNALDESK_FIXTURE_DIR", str(ROOT / "tests" / "fixtures"))
os.environ.setdefault("SIGNALDESK_DATA_DIR", str(ROOT / "demo" / "out" / "data"))

OUT = ROOT / "demo" / "out"
BOARD = OUT / "board.html"
HOST = os.environ.get("SIGNALDESK_DEMO_HOST", "127.0.0.1")
PORT = int(os.environ.get("SIGNALDESK_DEMO_PORT", "8765"))


def _ensure_demo(fresh: bool = False) -> None:
    data_dir = Path(os.environ["SIGNALDESK_DATA_DIR"])
    if fresh or not (data_dir / "signaldesk.sqlite").exists():
        if str(ROOT / "demo") not in sys.path:
            sys.path.insert(0, str(ROOT / "demo"))
        import run_demo
        raise_if = run_demo.main()
        if raise_if:
            raise SystemExit(raise_if)
    from boardhtml import render_board
    render_board(BOARD)


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    raw = json.dumps(payload, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("demo: " + (fmt % args) + "\n")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in {"/", "/board.html"}:
            from boardhtml import render_board
            dest = render_board(BOARD)
            data = dest.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/state":
            from boardhtml import board_payload
            _json(self, 200, board_payload())
            return
        if path.startswith("/vendor/ol/"):
            name = Path(path).name
            src = ROOT / "assets" / "vendor" / "ol" / name
            if name not in {"ol.js", "ol.css"} or not src.is_file():
                self.send_error(404, "not found")
                return
            data = src.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript" if name.endswith(".js") else "text/css")
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path.startswith("/exports/"):
            name = Path(path).name
            if name != Path(name).name or ".." in name:
                self.send_error(400, "bad name")
                return
            from paths import exports_dir
            dest = exports_dir() / name
            if not dest.is_file() or dest.suffix != ".eml":
                self.send_error(404, "no such file")
                return
            data = dest.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "message/rfc822")
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        import toolhandlers as tools
        from boardhtml import render_board

        parsed = urlparse(self.path)
        body = _read_json(self)
        lead_id = body.get("lead_id") or body.get("id") or ""
        routes = {
            "/api/draft": lambda: tools.signaldesk_draft({"lead_id": lead_id}),
            "/api/approve": lambda: tools.signaldesk_approve({"lead_id": lead_id}),
            "/api/mark": lambda: tools.signaldesk_mark({"lead_id": lead_id, "stage": body.get("stage"), "notes": body.get("notes")}),
            "/api/prepare": lambda: tools.signaldesk_prepare_send({"lead_id": lead_id}),
            "/api/map_scan": lambda: tools.signaldesk_map_scan({
                "city": body.get("city"), "business_type": body.get("business_type"),
                "bbox": body.get("bbox"), "limit": body.get("limit") or 40}),
        }
        fn = routes.get(parsed.path)
        if not fn:
            _json(self, 404, {"ok": False, "error": "unknown route"})
            return
        try:
            result = json.loads(fn())
        except Exception as exc:
            _json(self, 500, {"ok": False, "error": str(exc)})
            return
        try:
            render_board(BOARD)
        except Exception:
            pass
        code = 200 if result.get("ok", True) else 400
        _json(self, code, result)


def main() -> int:
    fresh = "--fresh" in sys.argv
    _ensure_demo(fresh=fresh)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"SignalDesk demo board: http://{HOST}:{PORT}/board.html")
    print("Record this URL. Approve / Copy / Open .eml call local handlers; nothing is sent.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
