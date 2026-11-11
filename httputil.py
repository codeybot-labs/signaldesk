"""Small HTTP helper with User-Agent, timeout, and optional fixture/file cache."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

USER_AGENT = "SignalDesk/0.1 (Hermes plugin; https://github.com/codeybot-labs/signaldesk)"
DEFAULT_TIMEOUT = 30


def _cache_dir() -> Optional[Path]:
    env = os.environ.get("SIGNALDESK_CACHE_DIR")
    if env:
        path = Path(env).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return None


def fixture_dir() -> Optional[Path]:
    env = os.environ.get("SIGNALDESK_FIXTURE_DIR")
    if env:
        return Path(env).expanduser()
    # Bundled fixtures next to the tests, also usable for offline demo
    bundled = Path(__file__).resolve().parent / "tests" / "fixtures"
    if os.environ.get("SIGNALDESK_OFFLINE") and bundled.is_dir():
        return bundled
    return None


def _slug(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", url)[:180]


def get_json(url: str, *, timeout: int = DEFAULT_TIMEOUT, fixture_name: Optional[str] = None,
             headers: Optional[dict[str, str]] = None) -> Any:
    """GET JSON. Prefers SIGNALDESK_FIXTURE_DIR/fixture_name when set (offline tests)."""
    fix = fixture_dir()
    if fix and fixture_name:
        path = fix / fixture_name
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    if os.environ.get("SIGNALDESK_OFFLINE"):
        raise RuntimeError(f"Offline mode: no fixture for {fixture_name or url}")

    cache = _cache_dir()
    cache_path = (cache / f"{_slug(url)}.json") if cache else None
    if cache_path and cache_path.is_file() and not os.environ.get("SIGNALDESK_NO_CACHE"):
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc
    data = json.loads(raw.decode("utf-8"))
    if cache_path:
        cache_path.write_text(json.dumps(data), encoding="utf-8")
    return data


def post_json(url: str, payload: dict[str, Any], *, headers: Optional[dict[str, str]] = None,
              timeout: int = DEFAULT_TIMEOUT) -> Any:
    if os.environ.get("SIGNALDESK_OFFLINE"):
        raise RuntimeError("Offline mode: POST disabled")
    body = json.dumps(payload).encode("utf-8")
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body_t = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body_t}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc.reason}") from exc
    return json.loads(raw.decode("utf-8"))
