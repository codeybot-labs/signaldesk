from models import ICP, Lead
from parse_hiring import parse_comment
from score import score_lead


def test_parse_standard_who_is_hiring_line():
    text = (
        "Simple Analytics | DevOps Engineer | REMOTE (worldwide, any timezone) | Full-time | "
        '<a href="https://www.simpleanalytics.com/jobs/devops">https://www.simpleanalytics.com/jobs/devops</a>'
        "<p>Hi HN, we are hiring. Contact us at jobs@simpleanalytics.com</p>"
    )
    parsed = parse_comment(text)
    assert parsed is not None
    assert parsed["company"] == "Simple Analytics"
    assert "DevOps" in parsed["role"]
    assert parsed["remote"] is True
    assert parsed["domain"] == "simpleanalytics.com"
    assert parsed["contact"] == "jobs@simpleanalytics.com"


def test_parse_onsite_and_ampersands():
    text = "Synteq | Growth Lead &amp; Systems Administrator | Austin, TX | REMOTE (US) | Full-time<p>We run hardware."
    parsed = parse_comment(text)
    assert parsed is not None
    assert parsed["company"] == "Synteq"
    assert "Austin" in parsed["location"]
    assert parsed["remote"] is True


def test_score_keyword_and_exclusion():
    icp = ICP(keywords=["analytics", "devops"], roles=["devops"], remote_ok=True, exclusions=["crypto"])
    good = Lead(
        id="a", company="Simple Analytics", domain="simpleanalytics.com",
        signal_type="hiring", signal_quote="Simple Analytics | DevOps Engineer | REMOTE",
        source_url="https://news.ycombinator.com/item?id=1", role="DevOps Engineer",
        remote=True, contact="jobs@simpleanalytics.com",
    )
    score, reasons = score_lead(good, icp)
    assert score >= 35
    assert any("keyword" in r for r in reasons)

    bad = Lead(
        id="b", company="Coin Casino", domain="example.com",
        signal_type="hiring", signal_quote="crypto casino dealers onsite only",
        source_url="https://example.com", remote=False,
    )
    icp2 = ICP(keywords=["developer tools"], remote_ok=True, onsite_ok=False, exclusions=["crypto", "casino"])
    score2, reasons2 = score_lead(bad, icp2)
    assert score2 < 35
    assert any("excluded" in r for r in reasons2)


def test_paragraph_does_not_leak_into_quote():
    text = (
        "Shepherd (Series B) | ONSITE | San Francisco, CA"
        "<p>At Shepherd, we&#x27;re pursuing the most ambitious technical vision."
    )
    parsed = parse_comment(text)
    assert parsed is not None
    assert parsed["company"] == "Shepherd"
    assert parsed["role"] == ""  # ONSITE is logistics, not a title
    assert "San Francisco" in parsed["location"]
    assert "ambitious" not in parsed["signal_quote"]
    assert "https://" not in parsed["signal_quote"]


def test_simple_analytics_quote_stays_on_the_header():
    text = (
        "Simple Analytics | DevOps Engineer | REMOTE (worldwide, any timezone) | Full-time | "
        '<a href="https://www.simpleanalytics.com/jobs/devops">https://www.simpleanalytics.com/jobs/devops</a>'
        "<p>Hi HN, we are hiring. Contact us at jobs@simpleanalytics.com</p>"
    )
    parsed = parse_comment(text)
    assert parsed["signal_quote"].startswith("Simple Analytics | DevOps Engineer")
    assert "Hi HN" not in parsed["signal_quote"]
    assert "https://" not in parsed["signal_quote"]


def test_company_url_in_parens_is_stripped():
    text = "Curiosity (https://curiosity.ai) | Forward Deployed Engineer | Toulouse, France | ONSITE<p>Hello"
    parsed = parse_comment(text)
    assert parsed["company"] == "Curiosity"
    assert "Forward Deployed" in parsed["role"]
    assert "(" not in parsed["company"]
