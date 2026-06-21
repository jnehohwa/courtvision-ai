#!/usr/bin/env python3
"""Validate Swift REST DTOs and client coverage against the OpenAPI contract."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OPENAPI_PATH = ROOT / "contracts" / "openapi.json"
SWIFT_MODELS_PATH = ROOT / "apps" / "ios" / "CourtVision" / "Models" / "APIModels.swift"
SWIFT_CLIENT_PATH = ROOT / "apps" / "ios" / "CourtVision" / "Networking" / "APIClient.swift"

SCHEMA_TO_SWIFT = {
    "GameResponse": "Game",
    "GamesResponse": "GamesResponse",
    "HealthResponse": "HealthResponse",
    "LiveSnapshotResponse": "LiveSnapshot",
    "PredictionResponse": "Prediction",
    "ReplayStartResponse": "ReplayStartResponse",
    "ShotAttemptRequest": "ShotAttemptRequest",
    "ShotQualityRequest": "ShotQualityRequest",
    "ShotQualityResponse": "ShotQualityResponse",
    "ShotQualityResult": "ShotQualityResult",
    "SourceHealthResponse": "SourceHealth",
    "TeamResponse": "Team",
    "TimelinePoint": "TimelinePoint",
}

IGNORED_SCHEMAS = {"HTTPValidationError", "ValidationError"}

EXPECTED_PUBLIC_CLIENT_METHODS = {
    ("GET", "/health"): "func health(",
    ("GET", "/api/v1/games"): "func games(",
    ("GET", "/api/v1/games/{game_id}"): "func game(gameID:",
    ("GET", "/api/v1/games/{game_id}/live"): "func liveSnapshot(gameID:",
    ("GET", "/api/v1/games/{game_id}/prediction"): "func prediction(gameID:",
    ("POST", "/api/v1/shot-quality"): "func shotQuality(",
}


def snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def swift_enum_raw_values(swift_source: str, enum_name: str) -> set[str]:
    enum_match = re.search(
        rf"enum\s+{re.escape(enum_name)}\s*:[^{{]+{{(?P<body>.*?)\n}}",
        swift_source,
        re.DOTALL,
    )
    if enum_match is None:
        raise ValueError(f"Missing Swift enum: {enum_name}")

    raw_values: set[str] = set()
    for case_match in re.finditer(
        r"^\s*case\s+(.+)$",
        enum_match.group("body"),
        re.MULTILINE,
    ):
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


def struct_body(swift_source: str, struct_name: str) -> str:
    match = re.search(rf"\bstruct\s+{re.escape(struct_name)}\b[^\{{]*\{{", swift_source)
    if match is None:
        raise ValueError(f"Missing Swift struct: {struct_name}")

    start = match.end()
    depth = 1
    for index, character in enumerate(swift_source[start:], start=start):
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return swift_source[start:index]

    raise ValueError(f"Unterminated Swift struct: {struct_name}")


def swift_struct_properties(swift_source: str, struct_name: str) -> dict[str, str]:
    body = struct_body(swift_source, struct_name)
    properties: dict[str, str] = {}
    for match in re.finditer(r"^\s*let\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([^\n=]+)", body, re.MULTILINE):
        properties[match.group(1)] = normalize_swift_type(match.group(2))
    return properties


def normalize_swift_type(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def swift_type(schema: dict[str, Any], openapi: dict[str, Any], *, required: bool) -> str:
    nullable = not required
    candidates = schema.get("anyOf")
    if isinstance(candidates, list):
        non_null = [candidate for candidate in candidates if candidate.get("type") != "null"]
        nullable = nullable or len(non_null) != len(candidates)
        if len(non_null) != 1:
            raise ValueError(f"Unsupported anyOf schema: {schema}")
        schema = non_null[0]

    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        base_type = (
            "SourceStatus"
            if ref_name == "SourceStatus"
            else SCHEMA_TO_SWIFT.get(ref_name)
        )
        if base_type is None:
            raise ValueError(f"No Swift type mapping for schema reference: {ref_name}")
    elif schema.get("type") == "array":
        item_type = swift_type(schema["items"], openapi, required=True)
        base_type = f"[{item_type}]"
    elif schema.get("type") == "object" and "additionalProperties" in schema:
        value_type = swift_type(schema["additionalProperties"], openapi, required=True)
        base_type = f"[String: {value_type}]"
    elif schema.get("type") == "string":
        base_type = "Date" if schema.get("format") == "date-time" else "String"
    elif schema.get("type") == "integer":
        base_type = "Int"
    elif schema.get("type") == "number":
        base_type = "Double"
    elif schema.get("type") == "boolean":
        base_type = "Bool"
    else:
        raise ValueError(f"Unsupported schema type: {schema}")

    return f"{base_type}?" if nullable else base_type


def expected_properties(schema_name: str, openapi: dict[str, Any]) -> dict[str, str]:
    schema = openapi["components"]["schemas"][schema_name]
    required = set(schema.get("required", []))
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError(f"Schema has no object properties: {schema_name}")

    expected: dict[str, str] = {}
    for json_name, property_schema in properties.items():
        expected[snake_to_camel(json_name)] = swift_type(
            property_schema,
            openapi,
            required=json_name in required,
        )
    return expected


def report_property_difference(
    schema_name: str,
    swift_name: str,
    expected: dict[str, str],
    actual: dict[str, str],
) -> bool:
    if expected == actual:
        return False

    print(
        f"{swift_name} does not match OpenAPI schema {schema_name}.",
        file=sys.stderr,
    )
    for name in sorted(expected.keys() - actual.keys()):
        print(f"  Missing in Swift: {name}: {expected[name]}", file=sys.stderr)
    for name in sorted(actual.keys() - expected.keys()):
        print(f"  Extra in Swift: {name}: {actual[name]}", file=sys.stderr)
    for name in sorted(expected.keys() & actual.keys()):
        if expected[name] != actual[name]:
            print(
                f"  Type mismatch for {name}: expected {expected[name]}, found {actual[name]}",
                file=sys.stderr,
            )
    return True


def report_set_difference(label: str, expected: set[str], actual: set[str]) -> bool:
    if expected == actual:
        return False

    print(f"{label} does not match OpenAPI.", file=sys.stderr)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        print(f"  Missing in Swift: {', '.join(missing)}", file=sys.stderr)
    if extra:
        print(f"  Extra in Swift: {', '.join(extra)}", file=sys.stderr)
    return True


def check_public_client_methods(openapi: dict[str, Any], swift_client: str) -> bool:
    failed = False
    public_paths = {
        (method.upper(), path)
        for path, methods in openapi["paths"].items()
        if not path.startswith("/internal/")
        for method in methods
    }
    expected_paths = set(EXPECTED_PUBLIC_CLIENT_METHODS.keys())

    failed |= report_set_difference(
        "Swift APIClient public REST endpoints",
        expected_paths,
        public_paths,
    )
    for endpoint, method_signature in EXPECTED_PUBLIC_CLIENT_METHODS.items():
        if endpoint not in public_paths:
            continue
        if method_signature not in swift_client:
            print(
                f"APIClient is missing Swift method for {endpoint[0]} {endpoint[1]}: {method_signature}",
                file=sys.stderr,
            )
            failed = True

    if "/internal/replays/" in swift_client:
        print(
            "APIClient must not expose the private replay-start command to the native app.",
            file=sys.stderr,
        )
        failed = True

    if ".convertFromSnakeCase" not in swift_client:
        print("APIClient decoder must preserve the OpenAPI snake_case mapping.", file=sys.stderr)
        failed = True
    if ".convertToSnakeCase" not in swift_client:
        print("APIClient encoder must preserve the OpenAPI snake_case mapping.", file=sys.stderr)
        failed = True

    return failed


def main() -> int:
    openapi = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    swift_models = SWIFT_MODELS_PATH.read_text(encoding="utf-8")
    swift_client = SWIFT_CLIENT_PATH.read_text(encoding="utf-8")

    schema_names = set(openapi["components"]["schemas"].keys()) - IGNORED_SCHEMAS - {"SourceStatus"}
    failed = report_set_difference(
        "Swift REST DTO schema coverage",
        schema_names,
        set(SCHEMA_TO_SWIFT.keys()),
    )

    source_status_enum = set(openapi["components"]["schemas"]["SourceStatus"]["enum"])
    failed |= report_set_difference(
        "SourceStatus",
        source_status_enum,
        swift_enum_raw_values(swift_models, "SourceStatus"),
    )

    for schema_name in sorted(schema_names & set(SCHEMA_TO_SWIFT.keys())):
        swift_name = SCHEMA_TO_SWIFT[schema_name]
        failed |= report_property_difference(
            schema_name,
            swift_name,
            expected_properties(schema_name, openapi),
            swift_struct_properties(swift_models, swift_name),
        )

    failed |= check_public_client_methods(openapi, swift_client)

    if failed:
        return 1

    print("iOS REST DTOs and APIClient methods match contracts/openapi.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
