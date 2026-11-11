"""ICP profile persistence (plugin data dir, optional Hermes config)."""

from __future__ import annotations

from typing import Any, Optional

from models import ICP
from store import kv_get, kv_set

_KEY = "icp"


def load_icp() -> ICP:
    return ICP.from_dict(kv_get(_KEY, {}) or {})


def save_icp(icp: ICP) -> ICP:
    kv_set(_KEY, icp.to_dict())
    return icp


def update_icp(patch: dict[str, Any]) -> ICP:
    current = load_icp().to_dict()
    incoming = ICP.from_dict(patch).to_dict()
    # Only overwrite fields the caller actually sent
    for key, val in patch.items():
        if key in incoming:
            current[key] = incoming[key]
    icp = ICP.from_dict(current)
    return save_icp(icp)
