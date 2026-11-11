"""LocalLead Map: OpenStreetMap businesses via Nominatim (geocode) + Overpass (POIs).

Policy notes (kept deliberately conservative):
- Nominatim: max 1 request/second, identifying User-Agent, results cached in the
  SQLite kv store (30 days). https://operations.osmfoundation.org/policies/nominatim/
- Overpass: one request at a time, server-side timeout, results cached (7 days),
  small result cap. Falls back to the bundled demo dataset when offline or on error.
- Data is © OpenStreetMap contributors, licensed ODbL 1.0. Attribution is attached to
  every map lead and written into CSV / .eml exports.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from store import kv_get, kv_set

PLUGIN_VERSION = "0.2.0"
USER_AGENT = f"SignalDesk-Hermes-plugin/{PLUGIN_VERSION} (+https://github.com/codeybot-labs/signaldesk)"
ATTRIBUTION = "© OpenStreetMap contributors, ODbL"
ATTRIBUTION_FULL = "© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)"
NOMINATIM_URL = os.environ.get("SIGNALDESK_NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
# Public Overpass instances, tried one after another (never in parallel).
# SIGNALDESK_OVERPASS_URL overrides the list (comma-separated), e.g. a regional
# instance such as https://overpass.osm.ch/api/interpreter (Switzerland only).
DEFAULT_OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)


def overpass_urls() -> list[str]:
    env = os.environ.get("SIGNALDESK_OVERPASS_URL", "").strip()
    if env:
        return [u.strip() for u in env.split(",") if u.strip()]
    return list(DEFAULT_OVERPASS_URLS)
NOMINATIM_MIN_INTERVAL = 1.0  # seconds between requests (policy: max 1/s)
NOMINATIM_TTL = 30 * 86400
OVERPASS_TTL = 7 * 86400
OVERPASS_TIMEOUT = 25  # server-side [timeout:]
HTTP_TIMEOUT = 40
MAX_RESULTS = 80
MAX_BBOX_DEG2 = 0.6  # refuse huge areas (roughly a large metro)

DEMO_DIR = Path(__file__).resolve().parent / "geodata"

# Friendly business type -> OSM tag (key, value)
BUSINESS_TYPES: dict[str, tuple[str, str]] = {
    "dentist": ("amenity", "dentist"),
    "doctor": ("amenity", "doctors"),
    "clinic": ("amenity", "clinic"),
    "pharmacy": ("amenity", "pharmacy"),
    "veterinary": ("amenity", "veterinary"),
    "cafe": ("amenity", "cafe"),
    "restaurant": ("amenity", "restaurant"),
    "bar": ("amenity", "bar"),
    "coworking": ("amenity", "coworking_space"),
    "bakery": ("shop", "bakery"),
    "hairdresser": ("shop", "hairdresser"),
    "beauty": ("shop", "beauty"),
    "florist": ("shop", "florist"),
    "bicycle": ("shop", "bicycle"),
    "gym": ("leisure", "fitness_centre"),
    "yoga": ("leisure", "fitness_centre"),
    "lawyer": ("office", "lawyer"),
    "accountant": ("office", "accountant"),
    "estate_agent": ("office", "estate_agent"),
    "it": ("office", "it"),
    "hotel": ("tourism", "hotel"),
}
_ALIASES = {
    "dentists": "dentist", "dental": "dentist", "coffee": "cafe", "cafes": "cafe", "coffee shop": "cafe",
    "restaurants": "restaurant", "gyms": "gym", "fitness": "gym", "lawyers": "lawyer", "law firm": "lawyer",
    "accountants": "accountant", "salon": "hairdresser", "barber": "hairdresser", "vet": "veterinary",
    "real estate": "estate_agent", "doctors": "doctor", "hotels": "hotel", "bakeries": "bakery",
    "coworking space": "coworking",
}

_NOMINATIM_LOCK = threading.Lock()
_OVERPASS_LOCK = threading.Lock()  # one Overpass request at a time
_last_nominatim = [0.0]

# Replaceable for tests: fn(url, data_bytes_or_None, headers) -> bytes
HttpFn = Callable[[str, Optional[bytes], dict], bytes]


def _default_http(url: str, data: Optional[bytes], headers: dict) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {urllib.parse.urlparse(url).netloc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


http_fn: HttpFn = _default_http
sleep_fn: Callable[[float], None] = time.sleep
clock_fn: Callable[[], float] = time.monotonic


def _offline() -> bool:
    # SIGNALDESK_GEO_ONLINE=1 lets the map reach OSM while the other sources stay on fixtures
    # (used by the recorded demo).
    if os.environ.get("SIGNALDESK_GEO_ONLINE", "").strip() in {"1", "true", "yes"}:
        return False
    return bool(os.environ.get("SIGNALDESK_OFFLINE"))


def resolve_type(business_type: str) -> tuple[str, str, str]:
    """Return (label, osm_key, osm_value). Accepts friendly names or raw 'key=value'."""
    raw = (business_type or "").strip().lower()
    if not raw:
        raise ValueError("business_type is required (e.g. 'dentist', 'cafe', or 'amenity=dentist')")
    m = re.fullmatch(r"([a-z_:]+)\s*=\s*([a-z0-9_;:-]+)", raw)
    if m:
        return m.group(2), m.group(1), m.group(2)
    raw = _ALIASES.get(raw, raw)
    if raw.endswith("s") and raw[:-1] in BUSINESS_TYPES:
        raw = raw[:-1]
    if raw in BUSINESS_TYPES:
        k, v = BUSINESS_TYPES[raw]
        return raw, k, v
    raise ValueError(
        f"Unknown business type {business_type!r}. Try one of: {', '.join(sorted(BUSINESS_TYPES))}, "
        "or a raw OSM tag like 'craft=brewery'."
    )


def _cache_get(key: str, ttl: int) -> Any:
    hit = kv_get(key)
    if isinstance(hit, dict) and "t" in hit and (time.time() - float(hit["t"])) < ttl:
        return hit.get("v")
    return None


def _cache_set(key: str, value: Any) -> None:
    kv_set(key, {"t": time.time(), "v": value})


def geocode(city: str) -> dict[str, Any]:
    """City name -> {name, bbox:[s,w,n,e], lat, lon}. Cached; rate-limited to 1 req/s."""
    q = re.sub(r"\s+", " ", (city or "").strip())
    if not q:
        raise ValueError("city is required")
    key = "geo:nominatim:" + q.lower()
    cached = _cache_get(key, NOMINATIM_TTL)
    if cached:
        return dict(cached, cached=True)
    if _offline():
        raise RuntimeError("offline: Nominatim disabled")
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1})
    with _NOMINATIM_LOCK:
        wait = NOMINATIM_MIN_INTERVAL - (clock_fn() - _last_nominatim[0])
        if wait > 0:
            sleep_fn(wait)
        try:
            raw = http_fn(url, None, {"User-Agent": USER_AGENT, "Accept": "application/json",
                                      "Accept-Language": "en"})
        finally:
            _last_nominatim[0] = clock_fn()
    rows = json.loads(raw.decode("utf-8"))
    if not rows:
        raise RuntimeError(f"Nominatim found no place named {q!r}")
    r = rows[0]
    s, n, w, e = (float(x) for x in r["boundingbox"])
    out = {"name": r.get("display_name") or q, "bbox": [s, w, n, e],
           "lat": float(r["lat"]), "lon": float(r["lon"])}
    _cache_set(key, out)
    return dict(out, cached=False)


def clamp_bbox(bbox: list[float], center: Optional[tuple[float, float]] = None) -> list[float]:
    """Shrink a giant bbox (e.g. a city boundary that includes far islands) around its center."""
    s, w, n, e = bbox
    if (n - s) * (e - w) <= MAX_BBOX_DEG2:
        return [s, w, n, e]
    lat, lon = center or ((s + n) / 2, (w + e) / 2)
    half = (MAX_BBOX_DEG2 ** 0.5) / 2
    return [max(s, lat - half), max(w, lon - half), min(n, lat + half), min(e, lon + half)]


def parse_bbox(value: Any) -> Optional[list[float]]:
    """Accept [s,w,n,e] list or 's,w,n,e' string. Returns None when absent."""
    if value in (None, "", []):
        return None
    if isinstance(value, str):
        value = [p for p in re.split(r"[,\s]+", value.strip()) if p]
    try:
        s, w, n, e = (float(x) for x in value)
    except (TypeError, ValueError):
        raise ValueError("bbox must be south,west,north,east in degrees")
    if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
        raise ValueError("bbox must be south,west,north,east with south<north and west<east")
    return [s, w, n, e]


def overpass_query(bbox: list[float], key: str, value: str, limit: int = MAX_RESULTS) -> str:
    s, w, n, e = bbox
    b = f"{s:.5f},{w:.5f},{n:.5f},{e:.5f}"
    sel = f'["{key}"="{value}"]["name"]'
    return (f"[out:json][timeout:{OVERPASS_TIMEOUT}];"
            f"(node{sel}({b});way{sel}({b}););out center tags {int(limit)};")


def fetch_pois(bbox: list[float], key: str, value: str, limit: int = MAX_RESULTS) -> dict[str, Any]:
    """Return {'elements': [...], 'cached': bool}. One request at a time; cached 7 days."""
    q = overpass_query(bbox, key, value, limit)
    ck = "geo:overpass:" + hashlib.sha1(q.encode()).hexdigest()[:16]
    cached = _cache_get(ck, OVERPASS_TTL)
    if cached is not None:
        return {"elements": cached, "cached": True}
    if _offline():
        raise RuntimeError("offline: Overpass disabled")
    raw = None
    errors = []
    with _OVERPASS_LOCK:
        for url in overpass_urls():
            try:
                raw = http_fn(url, urllib.parse.urlencode({"data": q}).encode(),
                              {"User-Agent": USER_AGENT, "Accept": "application/json",
                               "Content-Type": "application/x-www-form-urlencoded"})
                break
            except Exception as exc:
                errors.append(f"{urllib.parse.urlparse(url).netloc}: {exc}")
    if raw is None:
        raise RuntimeError("Overpass unreachable (" + "; ".join(errors)[:300] + ")")
    data = json.loads(raw.decode("utf-8"))
    if data.get("remark") and not data.get("elements"):
        raise RuntimeError(f"Overpass: {data['remark'][:160]}")
    elements = data.get("elements") or []
    _cache_set(ck, elements)
    return {"elements": elements, "cached": False}


# ---------- demo dataset ----------

def demo_datasets() -> list[dict[str, Any]]:
    out = []
    for path in sorted(DEMO_DIR.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in text if not unicodedata.combining(ch)).strip().lower()


def demo_lookup(city: str, value: str, bbox: Optional[list[float]]) -> Optional[dict[str, Any]]:
    """Find a bundled dataset matching the type and (city name or overlapping bbox)."""
    c = _fold(city)
    for ds in demo_datasets():
        if ds.get("osm_value") != value:
            continue
        ds_city = _fold(ds.get("city", ""))
        if c and (c in ds_city or ds_city.split(",")[0] in c):
            return ds
        if bbox and not c:
            s, w, n, e = bbox
            ds_s, ds_w, ds_n, ds_e = ds["bbox"]
            if not (e < ds_w or w > ds_e or n < ds_s or s > ds_n):
                els = [el for el in ds["elements"] if s <= _ll(el)[0] <= n and w <= _ll(el)[1] <= e]
                return dict(ds, elements=els)
    return None


# ---------- normalize ----------

def _ll(el: dict) -> tuple[float, float]:
    if "lat" in el:
        return float(el["lat"]), float(el["lon"])
    c = el.get("center") or {}
    return float(c.get("lat", 0)), float(c.get("lon", 0))


def _domain(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def element_to_poi(el: dict, label: str, key: str, value: str) -> Optional[dict[str, Any]]:
    tags = el.get("tags") or {}
    name = (tags.get("name") or "").strip()
    if not name:
        return None
    lat, lon = _ll(el)
    website = tags.get("website") or tags.get("contact:website") or tags.get("url") or ""
    email = tags.get("email") or tags.get("contact:email") or ""
    phone = tags.get("phone") or tags.get("contact:phone") or ""
    street = " ".join(p for p in [tags.get("addr:housenumber", ""), tags.get("addr:street", "")] if p)
    city = tags.get("addr:city", "")
    address = ", ".join(p for p in [street, city] if p)
    osm_type = el.get("type", "node")
    osm_id = el.get("id")
    return {
        "name": name, "lat": round(lat, 6), "lon": round(lon, 6),
        "business_type": label, "osm_tag": f"{key}={value}",
        "website": website.strip(), "email": email.split(";")[0].strip(), "phone": phone.split(";")[0].strip(),
        "address": address, "opening_hours": tags.get("opening_hours", ""),
        "osm_type": osm_type, "osm_id": osm_id,
        "osm_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
        "domain": _domain(website),
    }


def search(city: str = "", business_type: str = "", bbox: Any = None,
           limit: int = 40) -> dict[str, Any]:
    """Geocode (if needed) + Overpass with cache and demo fallback. Never hits the network twice
    for the same query within the cache TTL. Returns pois + metadata (mode: live|cache|demo)."""
    label, key, value = resolve_type(business_type)
    limit = max(1, min(int(limit or 40), MAX_RESULTS))
    box = parse_bbox(bbox)
    notes: list[str] = []
    place = None
    mode = "live"
    elements: list[dict] = []
    try:
        if box is None:
            place = geocode(city)
            box = clamp_bbox(place["bbox"], (place["lat"], place["lon"]))
        else:
            box = clamp_bbox(box)
        res = fetch_pois(box, key, value, limit)
        elements = res["elements"]
        mode = "cache" if res["cached"] else "live"
    except Exception as exc:
        ds = demo_lookup(city, value, box)
        if not ds:
            raise RuntimeError(f"OSM lookup failed ({exc}) and no bundled demo dataset matches "
                               f"{city or box} / {label}") from exc
        notes.append(f"Live OSM unavailable ({exc}); using the bundled demo dataset fetched "
                     f"{ds.get('fetched_at', '')}.")
        elements = ds["elements"]
        box = box or ds["bbox"]
        place = place or {"name": ds.get("city", city), "bbox": ds["bbox"]}
        mode = "demo"
    pois = [p for p in (element_to_poi(el, label, key, value) for el in elements) if p][:limit]
    return {
        "city": city or (place or {}).get("name", ""), "place": (place or {}).get("name", ""),
        "business_type": label, "osm_tag": f"{key}={value}", "bbox": box,
        "mode": mode, "notes": notes, "pois": pois, "attribution": ATTRIBUTION_FULL,
    }
