"""Source registry. Core sources are always registered; optional ones disable cleanly."""

from __future__ import annotations

from typing import Iterable, Optional

from sources.base import RawSignal, SignalSource, SourceMeta
from sources.hn_hiring import HNHiringSource
from sources.yc_hiring import YCHiringSource
from sources.hn_show import HNShowSource
from sources.hn_launch import HNLaunchSource
from sources.yc_launches import YCLaunchesSource

# Optional sources are imported lazily so a missing extra never breaks core.
_OPTIONAL = ("sources.producthunt",)


def all_sources() -> list[SignalSource]:
    items: list[SignalSource] = [
        HNHiringSource(),
        YCHiringSource(),
        HNShowSource(),
        YCLaunchesSource(),
        HNLaunchSource(),
    ]
    for mod_name in _OPTIONAL:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            factory = getattr(mod, "build", None)
            if factory:
                src = factory()
                if src is not None:
                    items.append(src)
        except Exception:
            continue
    return items


def sources_for(kind: str) -> list[SignalSource]:
    kind = (kind or "all").lower()
    out = []
    for src in all_sources():
        if kind in {"all", "everything"}:
            out.append(src)
        elif kind == "hiring" and src.meta.signal_type == "hiring":
            out.append(src)
        elif kind in {"launches", "launch"} and src.meta.signal_type == "launch":
            out.append(src)
        elif kind == src.meta.id:
            out.append(src)
    return out


def list_source_info() -> list[dict]:
    rows = []
    for src in all_sources():
        ok, reason = src.available()
        rows.append({
            "id": src.meta.id,
            "name": src.meta.name,
            "signal_type": src.meta.signal_type,
            "requires_env": list(src.meta.requires_env),
            "key_required": bool(src.meta.requires_env),
            "enabled": ok,
            "message": reason,
            "limits": src.meta.limits,
            "description": src.meta.description,
        })
    rows.append({
        "id": "osm_map",
        "name": "LocalLead Map (OSM)",
        "signal_type": "local",
        "requires_env": [],
        "key_required": False,
        "enabled": True,
        "message": "On demand: signaldesk_map_scan city + business type. © OpenStreetMap contributors, ODbL.",
        "limits": "Nominatim max 1 req/s, Overpass one request at a time; both cached.",
        "description": "Local businesses from OpenStreetMap via Overpass and Nominatim.",
    })
    return rows
