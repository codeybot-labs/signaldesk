"""Pluggable signal source interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class SourceMeta:
    id: str
    name: str
    signal_type: str  # hiring | launch
    requires_env: list[str] = field(default_factory=list)  # empty = keyless
    description: str = ""
    limits: str = ""
    enabled_reason: str = ""  # filled at list time


@dataclass
class RawSignal:
    """Normalized-enough record produced by a source, before ICP scoring / MX / store."""
    company: str
    domain: str = ""
    signal_type: str = ""
    signal_quote: str = ""
    source_url: str = ""
    source_id: str = ""
    contact: str = ""
    role: str = ""
    location: str = ""
    remote: Optional[bool] = None
    tags: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


class SignalSource(Protocol):
    meta: SourceMeta

    def available(self) -> tuple[bool, str]:
        """(enabled, message). Disabled sources must not raise later in fetch()."""
        ...

    def fetch(self) -> list[Any]:
        ...

    def normalize(self, raw: Any) -> Optional[RawSignal]:
        ...
