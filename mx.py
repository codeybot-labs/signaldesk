"""DNS MX lookup only. Never open an SMTP session or probe RCPT."""

from __future__ import annotations

import os
import socket
import struct
from typing import Optional

# Public resolvers used only if /etc/resolv.conf is unreadable.
_FALLBACK_NS = ("1.1.1.1", "8.8.8.8")


def _nameservers() -> list[str]:
    servers: list[str] = []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("nameserver"):
                    parts = line.split()
                    if len(parts) >= 2:
                        servers.append(parts[1])
    except OSError:
        pass
    return servers or list(_FALLBACK_NS)


def _encode_qname(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        raw = label.encode("idna")
        if len(raw) > 63:
            raise ValueError("DNS label too long")
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def _skip_name(buf: bytes, offset: int) -> int:
    while offset < len(buf):
        length = buf[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + (length & 0x3F)
    return offset


def lookup_mx(domain: str, timeout: float = 2.5) -> Optional[bool]:
    """Return True if the domain publishes MX (or an A/AAAA we treat as implicit mail),
    False if the lookup succeeded and found none, None if DNS failed.

    No SMTP. Results can be skipped with SIGNALDESK_SKIP_MX=1.
    """
    if os.environ.get("SIGNALDESK_SKIP_MX") == "1":
        return None
    domain = (domain or "").strip().rstrip(".").lower()
    if not domain or "." not in domain:
        return False
    try:
        question = _encode_qname(domain)
    except ValueError:
        return False
    # RFC 1035: header + QNAME + QTYPE=MX(15) + QCLASS=IN(1)
    msg = struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + question + struct.pack("!HH", 15, 1)
    for ns in _nameservers()[:2]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(msg, (ns, 53))
            data, _ = sock.recvfrom(512)
            sock.close()
        except OSError:
            continue
        if len(data) < 12:
            continue
        _id, flags, qd, an, _ns, _ar = struct.unpack("!HHHHHH", data[:12])
        rcode = flags & 0xF
        if rcode == 3:  # NXDOMAIN
            return False
        if rcode != 0:
            continue
        offset = 12
        for _ in range(qd):
            offset = _skip_name(data, offset) + 4
        if an > 0:
            return True
        # No MX records: many small domains still accept mail at the A record (RFC 5321 5.1).
        # We only report MX presence; no A-lookup "implicit MX" as True, to avoid overclaiming.
        return False
    return None
