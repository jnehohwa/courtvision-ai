#!/usr/bin/env python3
"""Validate Swift WebSocket enums against the shared JSON Schema contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "websocket-envelope.schema.json"
SWIFT_MODELS_PATH = ROOT / "apps" / "ios" / "CourtVision" / "Models" / "APIModels.swift"


def schema_enum(schema: dict[str, object], path: list[str]) -> set[str]:
    current: object = schema
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"Missing schema path: {'.'.join(path)}")
        current = current[key]

    if not isinstance(current, list) or not all(isinstance(value, str) for value in current):
        raise ValueError(f"Schema path is not a string enum: {'.'.join(path)}")

    return set(current)


def swift_enum_raw_values(swift_source: str, enum_name: str) -> set[str]:
    enum_match = re.search(
        rf"enum\s+{re.escape(enum_name)}\s*:[^{{]+{{(?P<body>.*?)\n}}",
        swift_source,
        re.DOTALL,
    )
    if enum_match is None:
        raise ValueError(f"Missing Swift enum: {enum_name}")

    raw_values: set[str] = set()
    for case_match in re.finditer(r"^\s*case\s+(.+)$", enum_match.group("body"), re.MULTILINE):
        for declaration in case_match.group(1).split(","):
            declaration = declaration.strip()
            if not declaration:
                continue

            name, _, explicit_value = declaration.partition("=")
            case_name = name.strip()
            string_literal_match = re.search(r'"([^"]+)"', explicit_value)
            raw_values.add(string_literal_match.group(1) if string_literal_match else case_name)

    if not raw_values:
        raise ValueError(f"Swift enum has no cases: {enum_name}")

    return raw_values


def report_difference(label: str, expected: set[str], actual: set[str]) -> bool:
    if expected == actual:
        return False

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    print(f"{label} does not match the shared WebSocket schema.", file=sys.stderr)
    if missing:
        print(f"  Missing in Swift: {', '.join(missing)}", file=sys.stderr)
    if extra:
        print(f"  Extra in Swift: {', '.join(extra)}", file=sys.stderr)
    return True


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    swift_source = SWIFT_MODELS_PATH.read_text(encoding="utf-8")

    failed = False
    failed |= report_difference(
        "WebSocketEventType",
        schema_enum(schema, ["properties", "type", "enum"]),
        swift_enum_raw_values(swift_source, "WebSocketEventType"),
    )
    failed |= report_difference(
        "SourceStatus",
        schema_enum(schema, ["properties", "source_status", "enum"]),
        swift_enum_raw_values(swift_source, "SourceStatus"),
    )

    if failed:
        return 1

    print("iOS WebSocket enums match contracts/websocket-envelope.schema.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
