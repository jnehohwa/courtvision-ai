from __future__ import annotations

import json
from pathlib import Path

from courtvision.main import app


def export_openapi(output: Path | None = None) -> Path:
    destination = output or Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


if __name__ == "__main__":
    print(export_openapi())
