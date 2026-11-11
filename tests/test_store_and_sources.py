from sources import list_source_info, sources_for
from store import kv_set, kv_get


def test_kv_roundtrip():
    kv_set("hello", {"a": 1})
    assert kv_get("hello") == {"a": 1}


def test_source_registry_lists_core_four():
    info = list_source_info()
    ids = [row["id"] for row in info]
    assert ids[:4] == ["hn_hiring", "yc_hiring", "hn_show", "yc_launches"]
    assert all(row["enabled"] for row in info if row["id"] in ids[:4])
    assert "producthunt" in ids
    ph = next(row for row in info if row["id"] == "producthunt")
    assert ph["enabled"] is False
    assert ph["key_required"] is True
    assert [s.meta.id for s in sources_for("hiring")] == ["hn_hiring", "yc_hiring"]
    assert [s.meta.id for s in sources_for("launches")][:2] == ["hn_show", "yc_launches"]


def test_launch_hn_title_parsing_and_offline_scan():
    from pipeline import scan
    from sources.hn_launch import parse_title
    assert parse_title("Launch HN: Rivet (YC W23) – Scale and Orchestrate Agents on S3") == (
        "Rivet", "W23", "Scale and Orchestrate Agents on S3")
    assert parse_title("Show HN: nope") == ("", "", "")
    report = scan(kind="hn_launch")
    assert report["ok"] and report["inserted"] >= 10
