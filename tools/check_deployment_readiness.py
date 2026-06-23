#!/usr/bin/env python3
"""Validate the Vercel/Render handoff before claiming deployment readiness."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_WEB_ENV = {
    "NEXT_PUBLIC_API_URL",
    "NEXT_PUBLIC_WS_URL",
    "COURTVISION_INTERNAL_API_URL",
    "COURTVISION_INTERNAL_API_KEY",
}

REQUIRED_RENDER_SERVICES = {
    "courtvision-redis": "keyvalue",
    "courtvision-api": "web",
    "courtvision-replay-worker": "worker",
    "courtvision-daily-ingestion": "cron",
}


class DeploymentCheck:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.failures.append(message)

    def finish(self) -> int:
        if not self.failures:
            print("Deployment readiness preflight passed.")
            return 0

        print("Deployment readiness preflight failed:", file=sys.stderr)
        for failure in self.failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_render_blueprint() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("render.yaml must contain a mapping at the top level")
    return data


def service_by_name(blueprint: dict[str, Any], name: str) -> dict[str, Any]:
    services = blueprint.get("services")
    if not isinstance(services, list):
        raise ValueError("render.yaml must define a services list")
    for service in services:
        if isinstance(service, dict) and service.get("name") == name:
            return service
    raise KeyError(name)


def env_vars_by_key(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    env_vars = service.get("envVars")
    if not isinstance(env_vars, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for env_var in env_vars:
        if isinstance(env_var, dict) and isinstance(env_var.get("key"), str):
            result[env_var["key"]] = env_var
    return result


def check_value(
    check: DeploymentCheck,
    env_vars: dict[str, dict[str, Any]],
    key: str,
    expected: str,
    *,
    service: str,
) -> None:
    actual = env_vars.get(key, {}).get("value")
    check.require(
        actual == expected,
        f"{service} must set {key}={expected!r}; found {actual!r}",
    )


def check_database_reference(
    check: DeploymentCheck,
    env_vars: dict[str, dict[str, Any]],
    key: str,
    *,
    service: str,
) -> None:
    reference = env_vars.get(key, {}).get("fromDatabase")
    check.require(
        reference == {"name": "courtvision-postgres", "property": "connectionString"},
        f"{service} must source {key} from courtvision-postgres.connectionString",
    )


def check_redis_reference(
    check: DeploymentCheck,
    env_vars: dict[str, dict[str, Any]],
    key: str,
    *,
    service: str,
) -> None:
    reference = env_vars.get(key, {}).get("fromService")
    check.require(
        reference
        == {
            "type": "keyvalue",
            "name": "courtvision-redis",
            "property": "connectionString",
        },
        f"{service} must source {key} from courtvision-redis.connectionString",
    )


def check_sync_false(
    check: DeploymentCheck,
    env_vars: dict[str, dict[str, Any]],
    key: str,
    *,
    service: str,
) -> None:
    actual = env_vars.get(key, {}).get("sync")
    check.require(
        actual is False,
        f"{service} must mark {key} as sync: false for dashboard-managed deployment values",
    )


def check_vercel(check: DeploymentCheck) -> None:
    vercel_config = read_json(ROOT / "apps" / "web" / "vercel.json")
    web_package = read_json(ROOT / "apps" / "web" / "package.json")
    root_package = read_json(ROOT / "package.json")
    next_config = read_text(ROOT / "apps" / "web" / "next.config.ts")
    replay_route = read_text(
        ROOT / "apps" / "web" / "src" / "app" / "api" / "replay" / "route.ts"
    )
    env_example = read_text(ROOT / ".env.example")
    gitignore = read_text(ROOT / ".gitignore")

    check.require(
        vercel_config.get("installCommand") == "cd ../.. && pnpm install --frozen-lockfile",
        "apps/web/vercel.json must install from the monorepo root with a frozen pnpm lockfile",
    )
    check.require(
        vercel_config.get("buildCommand") == "pnpm build",
        "apps/web/vercel.json must run the web package build script",
    )
    check.require(
        web_package.get("scripts", {}).get("build") == "next build",
        "@courtvision/web build script must run next build",
    )
    check.require(
        root_package.get("packageManager") == "pnpm@10.12.1",
        "root package.json must pin the pnpm version used by CI and Vercel",
    )
    check.require(
        'output: "standalone"' in next_config,
        "Next.js config must keep standalone output enabled for deployment packaging",
    )
    check.require(
        "poweredByHeader: false" in next_config,
        "Next.js config must keep the X-Powered-By header disabled",
    )
    for env_key in sorted(REQUIRED_WEB_ENV):
        check.require(
            f"{env_key}=" in env_example,
            f".env.example must document {env_key}",
        )
    check.require(
        'env.NODE_ENV === "production"' in replay_route
        and "COURTVISION_INTERNAL_API_URL" in replay_route
        and "COURTVISION_INTERNAL_API_KEY" in replay_route
        and "DEVELOPMENT_INTERNAL_API_KEY" in replay_route
        and "MINIMUM_PRODUCTION_KEY_LENGTH" in replay_route
        and "Replay service is not configured" in replay_route,
        "apps/web replay proxy must reject unconfigured or development-key production replay starts",
    )
    check.require(
        ".vercel/" in gitignore,
        ".gitignore must exclude local Vercel project linkage",
    )


def check_render(check: DeploymentCheck) -> None:
    blueprint = load_render_blueprint()
    databases = blueprint.get("databases")
    check.require(isinstance(databases, list), "render.yaml must define databases")
    database = next(
        (item for item in databases or [] if isinstance(item, dict) and item.get("name") == "courtvision-postgres"),
        None,
    )
    check.require(database is not None, "render.yaml must define courtvision-postgres")
    if isinstance(database, dict):
        check.require(
            database.get("databaseName") == "courtvision",
            "courtvision-postgres must use databaseName courtvision",
        )
        check.require(
            database.get("user") == "courtvision",
            "courtvision-postgres must use user courtvision",
        )

    for name, service_type in REQUIRED_RENDER_SERVICES.items():
        try:
            service = service_by_name(blueprint, name)
        except KeyError:
            check.require(False, f"render.yaml must define service {name}")
            continue
        check.require(
            service.get("type") == service_type,
            f"{name} must be a Render {service_type} service",
        )

    api = service_by_name(blueprint, "courtvision-api")
    worker = service_by_name(blueprint, "courtvision-replay-worker")
    cron = service_by_name(blueprint, "courtvision-daily-ingestion")

    check.require(
        api.get("runtime") == "docker"
        and api.get("dockerfilePath") == "./apps/api/Dockerfile",
        "courtvision-api must deploy from apps/api/Dockerfile",
    )
    check.require(
        api.get("healthCheckPath") == "/health",
        "courtvision-api must expose /health as its Render health check",
    )
    check.require(
        api.get("preDeployCommand") == "alembic upgrade head",
        "courtvision-api must run Alembic before deploy",
    )
    check.require(
        api.get("initialDeployHook") == "python -m courtvision.seed",
        "courtvision-api must seed the deterministic fixture on initial deploy",
    )

    api_env = env_vars_by_key(api)
    worker_env = env_vars_by_key(worker)
    cron_env = env_vars_by_key(cron)
    for service_name, env_vars in (
        ("courtvision-api", api_env),
        ("courtvision-replay-worker", worker_env),
        ("courtvision-daily-ingestion", cron_env),
    ):
        check_database_reference(
            check,
            env_vars,
            "COURTVISION_DATABASE_URL",
            service=service_name,
        )
        check_value(
            check,
            env_vars,
            "COURTVISION_ENVIRONMENT",
            "production",
            service=service_name,
        )

    for service_name, env_vars in (
        ("courtvision-api", api_env),
        ("courtvision-replay-worker", worker_env),
        ("courtvision-daily-ingestion", cron_env),
    ):
        check_redis_reference(
            check,
            env_vars,
            "COURTVISION_REDIS_URL",
            service=service_name,
        )

    check_sync_false(
        check,
        api_env,
        "COURTVISION_INTERNAL_API_KEY",
        service="courtvision-api",
    )
    check_sync_false(
        check,
        api_env,
        "COURTVISION_CORS_ORIGINS",
        service="courtvision-api",
    )
    check_value(
        check,
        api_env,
        "COURTVISION_TRUST_PROXY_HEADERS",
        "true",
        service="courtvision-api",
    )
    check_value(
        check,
        api_env,
        "COURTVISION_ENABLE_DELAYED_LIVE",
        "false",
        service="courtvision-api",
    )
    check.require(
        worker.get("dockerCommand") == "python -m courtvision.worker",
        "courtvision-replay-worker must run the replay worker command",
    )
    check.require(
        cron.get("dockerCommand") == "python -m courtvision.ingest",
        "courtvision-daily-ingestion must run the ingestion command",
    )
    check.require(
        cron.get("schedule") == "15 8 * * *",
        "courtvision-daily-ingestion schedule must remain explicit",
    )
    check_value(
        check,
        cron_env,
        "COURTVISION_ENABLE_DELAYED_LIVE",
        "false",
        service="courtvision-daily-ingestion",
    )


def check_dependencies(check: DeploymentCheck) -> None:
    api_pyproject = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text())
    dev_dependencies = set(api_pyproject["project"]["optional-dependencies"]["dev"])
    check.require(
        any(dependency.startswith("pyyaml") for dependency in dev_dependencies),
        "apps/api dev dependencies must include PyYAML for deployment preflight parsing",
    )


def main() -> int:
    check = DeploymentCheck()
    check_dependencies(check)
    check_vercel(check)
    check_render(check)
    return check.finish()


if __name__ == "__main__":
    raise SystemExit(main())
