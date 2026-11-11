"""LocalLead Map: mocked Nominatim/Overpass, rate limit, cache, demo fallback, attribution."""
import csv
import json

import pytest

import geo
import toolhandlers as tools
from icp import save_icp
from models import ICP
from store import get_lead

NOMINATIM = [{"display_name": "Testville", "lat": "47.37", "lon": "8.54",
              "boundingbox": ["47.30", "47.45", "8.45", "8.63"]}]
OVERPASS = {"elements": [
    {"type": "node", "id": 1, "lat": 47.371, "lon": 8.541,
     "tags": {"name": "Smile Dental", "amenity": "dentist", "website": "https://smile.example",
              "email": "hi@smile.example", "phone": "+41 44 000 00 00", "opening_hours": "Mo-Fr 08:00-18:00",
              "addr:street": "Bahnhofstrasse", "addr:housenumber": "1"}},
    {"type": "way", "id": 2, "center": {"lat": 47.38, "lon": 8.55},
     "tags": {"name": "Bare Dentist", "amenity": "dentist"}},
    {"type": "node", "id": 3, "lat": 47.39, "lon": 8.56, "tags": {"amenity": "dentist"}},  # no name
]}


class FakeNet:
    def __init__(self):
        self.calls = []
        self.now = 1000.0
        self.slept = []
        self.fail_overpass = False

    def http(self, url, data, headers):
        self.calls.append((url, data, headers))
        assert headers["User-Agent"].startswith("SignalDesk-Hermes-plugin/")
        assert "github.com/codeybot-labs/signaldesk" in headers["User-Agent"]
        if "nominatim" in url:
            return json.dumps(NOMINATIM).encode()
        if self.fail_overpass:
            raise RuntimeError("Network error: boom")
        return json.dumps(OVERPASS).encode()

    def sleep(self, s):
        self.slept.append(s)
        self.now += s

    def clock(self):
        return self.now


@pytest.fixture
def net(monkeypatch):
    fake = FakeNet()
    monkeypatch.delenv("SIGNALDESK_OFFLINE", raising=False)
    monkeypatch.setenv("SIGNALDESK_OVERPASS_URL", "https://overpass.test/api/interpreter")
    monkeypatch.setattr(geo, "http_fn", fake.http)
    monkeypatch.setattr(geo, "sleep_fn", fake.sleep)
    monkeypatch.setattr(geo, "clock_fn", fake.clock)
    monkeypatch.setattr(geo, "_last_nominatim", [0.0])
    save_icp(ICP(business_types=["dentist"], local_offer="a booking assistant", sender_name="Alex"))
    return fake


def test_resolve_type_aliases_and_raw_tags():
    assert geo.resolve_type("Dentists")[1:] == ("amenity", "dentist")
    assert geo.resolve_type("coffee")[1:] == ("amenity", "cafe")
    assert geo.resolve_type("craft=brewery")[1:] == ("craft", "brewery")
    with pytest.raises(ValueError):
        geo.resolve_type("spaceport")


def test_parse_and_clamp_bbox():
    assert geo.parse_bbox("47.3,8.4,47.4,8.6") == [47.3, 8.4, 47.4, 8.6]
    with pytest.raises(ValueError):
        geo.parse_bbox("47.4,8.4,47.3,8.6")
    big = geo.clamp_bbox([30.0, -10.0, 50.0, 10.0], (40.0, 0.0))
    assert (big[2] - big[0]) * (big[3] - big[1]) <= geo.MAX_BBOX_DEG2 + 1e-9


def test_map_scan_live_scores_and_caches(net):
    out = json.loads(tools.signaldesk_map_scan({"city": "Testville", "business_type": "dentist"}))
    assert out["ok"] is True and out["mode"] == "live"
    assert out["found"] == 2  # unnamed element dropped
    assert "OpenStreetMap" in out["attribution"] and "ODbL" in out["attribution"]
    n_calls = len(net.calls)
    assert n_calls == 2  # one Nominatim + one Overpass
    smile = next(l for l in out["leads"] if l["company"] == "Smile Dental")
    bare = next(l for l in out["leads"] if l["company"] == "Bare Dentist")
    assert smile["score"] > bare["score"]
    lead = get_lead(smile["id"])
    assert lead.signal_type == "local" and lead.contact == "hi@smile.example"
    assert lead.domain == "smile.example"
    assert "business type matched: dentist" in lead.score_reasons
    assert lead.provenance["osm_url"] == "https://www.openstreetmap.org/node/1"
    # Same query again: served from the SQLite cache, no network.
    again = json.loads(tools.signaldesk_map_scan({"city": "Testville", "business_type": "dentist"}))
    assert again["mode"] == "cache"
    assert len(net.calls) == n_calls


def test_nominatim_rate_limit_one_per_second(net):
    geo.geocode("Alpha")
    net.now += 0.2  # next request only 0.2 s later
    geo.geocode("Beta")
    assert net.slept and net.slept[-1] == pytest.approx(0.8, abs=1e-6)
    geo.geocode("Alpha")  # cached: no request, no sleep
    assert sum(1 for c in net.calls if "nominatim" in c[0]) == 2
    assert len(net.slept) == 1


def test_overpass_failure_falls_back_to_bundled_demo(net):
    net.fail_overpass = True
    out = json.loads(tools.signaldesk_map_scan({"city": "Zürich", "business_type": "dentist"}))
    assert out["ok"] is True and out["mode"] == "demo"
    assert out["found"] >= 20
    assert out["notes"] and "demo dataset" in out["notes"][0]


def test_offline_bbox_uses_demo_subset(monkeypatch):
    save_icp(ICP(business_types=["cafe"]))
    out = json.loads(tools.signaldesk_map_scan({"bbox": "47.36,8.52,47.39,8.56", "business_type": "cafe"}))
    assert out["ok"] is True and out["mode"] == "demo"
    for l in out["leads"]:
        assert 47.36 <= l["lat"] <= 47.39 and 8.52 <= l["lon"] <= 8.56


def test_map_scan_validates_input():
    assert json.loads(tools.signaldesk_map_scan({"city": "Zürich"}))["ok"] is False
    assert json.loads(tools.signaldesk_map_scan({"business_type": "cafe"}))["ok"] is False
    bad = json.loads(tools.signaldesk_map_scan({"city": "Zürich", "business_type": "spaceport"}))
    assert bad["ok"] is False and "Unknown business type" in bad["error"]


def test_map_lead_draft_references_osm_and_exports_carry_attribution(net):
    out = json.loads(tools.signaldesk_map_scan({"city": "Testville", "business_type": "dentist"}))
    smile = next(l for l in out["leads"] if l["company"] == "Smile Dental")
    drafted = json.loads(tools.signaldesk_draft({"lead_id": smile["id"]}))
    body = drafted["lead"]["draft_body"]
    assert "OpenStreetMap" in body and "Bahnhofstrasse" in body and "smile.example" in body
    assert "a booking assistant" in body
    # Not approved -> prepare_send refuses (draft-first gate unchanged)
    refused = json.loads(tools.signaldesk_prepare_send({"lead_id": smile["id"]}))
    assert refused["ok"] is False
    tools.signaldesk_approve({"lead_id": smile["id"]})
    prepared = json.loads(tools.signaldesk_prepare_send({"lead_id": smile["id"]}))
    assert prepared["ok"] is True and prepared["sent"] is False
    eml = open(prepared["eml_path"], encoding="utf-8").read()
    assert "X-SignalDesk-Data-Attribution: © OpenStreetMap contributors, ODbL" in eml
    exported = json.loads(tools.signaldesk_export_csv({}))
    assert "ODbL" in exported["attribution"]
    rows = list(csv.DictReader(open(exported["path"], encoding="utf-8")))
    osm_rows = [r for r in rows if r["signal_type"] == "local"]
    assert osm_rows and all("© OpenStreetMap contributors, ODbL" in r["attribution"] for r in osm_rows)
    assert rows[-1]["id"] == "#" and "OpenStreetMap" in rows[-1]["company"]


def test_hiring_exports_have_no_osm_attribution():
    from pipeline import scan
    scan(kind="hn_hiring")
    exported = json.loads(tools.signaldesk_export_csv({}))
    rows = list(csv.DictReader(open(exported["path"], encoding="utf-8")))
    assert rows and all(r["attribution"] == "" for r in rows)
    assert exported["attribution"] == ""


def test_sources_list_includes_map_and_schema_registered():
    import schemas
    srcs = json.loads(tools.signaldesk_sources({}))["sources"]
    assert any(s["id"] == "osm_map" and not s["key_required"] for s in srcs)
    names = {s["name"] for s in schemas.ALL_SCHEMAS}
    assert "signaldesk_map_scan" in names and "signaldesk_map_scan" in tools.HANDLERS


def test_board_contains_map_and_attribution(tmp_path):
    from boardhtml import render_board
    path = render_board(tmp_path / "board.html")
    html = path.read_text(encoding="utf-8")
    assert 'id="map"' in html and "vendor/ol/ol.js" in html
    assert "OpenStreetMap" in html and "ODbL" in html
    assert (tmp_path / "vendor" / "ol" / "ol.js").is_file()


def test_desktop_bundle_passes_surface_lint():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "desktop" / "plugin.js").read_text(encoding="utf-8")
    assert "MapPanel" in src and "OpenLayers 10.5.0" in src
    assert 'createElement("script")' not in src and "createElement('script')" not in src


def test_overpass_bad_body_retries_once_then_succeeds(net, monkeypatch):
    calls = {"n": 0}
    good = net.http

    def flaky(url, data, headers):
        if "overpass" in url:
            calls["n"] += 1
            if calls["n"] == 1:
                return b"<html>busy</html>"
        return good(url, data, headers)

    monkeypatch.setattr(geo, "http_fn", flaky)
    out = json.loads(tools.signaldesk_map_scan({"city": "Testville", "business_type": "dentist"}))
    assert out["mode"] == "live" and out["found"] == 2
    assert calls["n"] == 2 and geo.OVERPASS_RETRY_PAUSE in net.slept
