#!/usr/bin/env python3
"""Report whether CourtVision AI is linked or deployed to Vercel.

This command is intentionally read-only. It verifies public deployment evidence
without changing local Vercel linkage, creating deployments, or requiring Vercel
credentials.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPOSITORY = "jnehohwa/courtvision-ai"
RunCommand = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class DeploymentState:
    repository: str
    commit: str | None
    github_deployments: list[dict[str, Any]] = field(default_factory=list)
    check_runs: list[dict[str, Any]] = field(default_factory=list)
    vercel_project_linked: bool = False
    vercel_cli_available: bool = False

    @property
    def has_github_deployments(self) -> bool:
        return len(self.github_deployments) > 0

    @property
    def has_vercel_check_runs(self) -> bool:
        return any(is_vercel_check_run(check_run) for check_run in self.check_runs)

    @property
    def is_deployed_to_vercel(self) -> bool:
        return self.has_github_deployments or self.has_vercel_check_runs


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def load_json_output(result: subprocess.CompletedProcess[str], *, fallback: Any) -> Any:
    if result.returncode != 0:
        return fallback
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError:
        return fallback


def current_commit(run: RunCommand = run_command) -> str | None:
    result = run(["git", "rev-parse", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def github_deployments(repository: str, run: RunCommand = run_command) -> list[dict[str, Any]]:
    result = run(
        [
            "gh",
            "api",
            f"repos/{repository}/deployments",
            "--jq",
            ".",
        ]
    )
    deployments = load_json_output(result, fallback=[])
    if isinstance(deployments, list):
        return [item for item in deployments if isinstance(item, dict)]
    return []


def github_check_runs(
    repository: str,
    commit: str | None,
    run: RunCommand = run_command,
) -> list[dict[str, Any]]:
    if not commit:
        return []
    result = run(
        [
            "gh",
            "api",
            f"repos/{repository}/commits/{commit}/check-runs",
            "--jq",
            ".check_runs",
        ]
    )
    check_runs = load_json_output(result, fallback=[])
    if isinstance(check_runs, list):
        return [item for item in check_runs if isinstance(item, dict)]
    return []


def is_vercel_check_run(check_run: dict[str, Any]) -> bool:
    app = check_run.get("app")
    app_slug = app.get("slug") if isinstance(app, dict) else None
    name = str(check_run.get("name", "")).lower()
    details_url = str(check_run.get("details_url", "")).lower()
    return app_slug == "vercel" or "vercel" in name or "vercel" in details_url


def load_deployment_state(
    *,
    repository: str = DEFAULT_REPOSITORY,
    root: Path = ROOT,
    run: RunCommand = run_command,
) -> DeploymentState:
    commit = current_commit(run)
    return DeploymentState(
        repository=repository,
        commit=commit,
        github_deployments=github_deployments(repository, run),
        check_runs=github_check_runs(repository, commit, run),
        vercel_project_linked=(root / ".vercel" / "project.json").exists(),
        vercel_cli_available=shutil.which("vercel") is not None,
    )


def summarize_state(state: DeploymentState) -> str:
    lines = [
        "CourtVision AI public deployment state",
        f"- Repository: {state.repository}",
        f"- Commit: {state.commit or 'unknown'}",
        f"- GitHub deployments: {len(state.github_deployments)}",
        f"- Vercel check-runs on commit: {'yes' if state.has_vercel_check_runs else 'no'}",
        f"- Local Vercel project link: {'yes' if state.vercel_project_linked else 'no'}",
        f"- Vercel CLI on PATH: {'yes' if state.vercel_cli_available else 'no'}",
    ]
    if state.is_deployed_to_vercel:
        lines.append("- Verdict: deployment evidence found")
    else:
        lines.append("- Verdict: not deployed to Vercel yet")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        default=DEFAULT_REPOSITORY,
        help=f"GitHub repository to inspect, default: {DEFAULT_REPOSITORY}",
    )
    args = parser.parse_args()
    state = load_deployment_state(repository=args.repository)
    print(summarize_state(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
