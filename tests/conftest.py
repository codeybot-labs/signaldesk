import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNALDESK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SIGNALDESK_FIXTURE_DIR", str(ROOT / "tests" / "fixtures"))
    monkeypatch.setenv("SIGNALDESK_OFFLINE", "1")
    monkeypatch.setenv("SIGNALDESK_SKIP_MX", "1")
    monkeypatch.delenv("SIGNALDESK_CACHE_DIR", raising=False)
    yield
