from __future__ import annotations

import json
from pathlib import Path

from courtvision.main import app


def test_committed_openapi_matches_application():
    contract_path = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"
    committed = json.loads(contract_path.read_text(encoding="utf-8"))
    assert committed == app.openapi()
