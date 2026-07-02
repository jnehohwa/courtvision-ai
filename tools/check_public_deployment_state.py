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
class GitHubQuery:
    items: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class DeploymentState:
    repository: str
    commit: str | None
    github_deployments: GitHubQuery = field(default_factory=GitHubQuery)
    check_runs: GitHubQuery = field(default_factory=GitHubQuery)
    vercel_project_linked: bool = False
    vercel_cli_available: bool = False

    @property
    def has_github_deployments(self) -> bool:
        return len(self.github_deployments.items) > 0

    @property
    def has_vercel_check_runs(self) -> bool:
        return any(is_vercel_check_run(check_run) for check_run in self.check_runs.items)

    @property
    def evidence_available(self) -> bool:
        return self.github_deployments.available and self.check_runs.available

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


def command_error(result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout).strip()
    if detail:
        return f"command exited {result.returncode}: {detail}"
    return f"command exited {result.returncode}"


def load_json_list(result: subprocess.CompletedProcess[str]) -> GitHubQuery:
    if result.returncode != 0:
        return GitHubQuery(error=command_error(result))
    try:
        payload = json.loads(result.stdout or "null")
    except json.JSONDecodeError as exc:
        return GitHubQuery(error=f"invalid JSON: {exc.msg}")
    if not isinstance(payload, list):
        return GitHubQuery(error=f"expected a JSON list, got {type(payload).__name__}")
    return GitHubQuery(items=[item for item in payload if isinstance(item, dict)])


def current_commit(run: RunCommand = run_command) -> str | None:
    result = run(["git", "rev-parse", "HEAD"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def github_deployments(repository: str, run: RunCommand = run_command) -> GitHubQuery:
    result = run(
        [
            "gh",
            "api",
            f"repos/{repository}/deployments",
            "--jq",
            ".",
        ]
    )
    return load_json_list(result)


def github_check_runs(
    repository: str,
    commit: str | None,
    run: RunCommand = run_command,
) -> GitHubQuery:
    if not commit:
        return GitHubQuery(error="current commit unavailable")
    result = run(
        [
            "gh",
            "api",
            f"repos/{repository}/commits/{commit}/check-runs",
            "--jq",
            ".check_runs",
        ]
    )
    return load_json_list(result)


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
        f"- GitHub deployments: {deployment_count_summary(state.github_deployments)}",
        f"- Vercel check-runs on commit: {check_run_summary(state)}",
        f"- Local Vercel project link: {'yes' if state.vercel_project_linked else 'no'}",
        f"- Vercel CLI on PATH: {'yes' if state.vercel_cli_available else 'no'}",
    ]
    if state.is_deployed_to_vercel:
        lines.append("- Verdict: deployment evidence found")
    elif not state.evidence_available:
        lines.append("- Verdict: unable to confirm deployment state")
    else:
        lines.append("- Verdict: not deployed to Vercel yet")
    return "\n".join(lines)


def deployment_count_summary(query: GitHubQuery) -> str:
    if query.error:
        return f"unknown ({query.error})"
    return str(len(query.items))


def check_run_summary(state: DeploymentState) -> str:
    if state.check_runs.error:
        return f"unknown ({state.check_runs.error})"
    return "yes" if state.has_vercel_check_runs else "no"


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
