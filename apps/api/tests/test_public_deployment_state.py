from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "tools" / "check_public_deployment_state.py"
SPEC = importlib.util.spec_from_file_location("check_public_deployment_state", MODULE_PATH)
assert SPEC is not None
LOADER = SPEC.loader
assert LOADER is not None
deployment_state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deployment_state
LOADER.exec_module(deployment_state)

DeploymentState = deployment_state.DeploymentState
GitHubQuery = deployment_state.GitHubQuery
is_vercel_check_run = deployment_state.is_vercel_check_run
load_deployment_state = deployment_state.load_deployment_state
summarize_state = deployment_state.summarize_state


def completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


def test_detects_vercel_check_runs_from_app_slug() -> None:
    assert is_vercel_check_run({"name": "Preview", "app": {"slug": "vercel"}})
    assert is_vercel_check_run({"name": "Vercel", "details_url": "https://vercel.com/x/y"})
    assert not is_vercel_check_run({"name": "backend", "app": {"slug": "github-actions"}})


def test_load_state_without_deployment_evidence(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return completed("abc123\n")
        if "deployments" in command[2]:
            return completed("[]")
        if "check-runs" in command[2]:
            return completed('[{"name":"backend","app":{"slug":"github-actions"}}]')
        raise AssertionError(f"unexpected command: {command}")

    state = load_deployment_state(repository="owner/repo", root=tmp_path, run=run)

    assert state.commit == "abc123"
    assert state.github_deployments.items == []
    assert state.github_deployments.error is None
    assert not state.has_vercel_check_runs
    assert not state.vercel_project_linked
    assert not state.is_deployed_to_vercel
    assert calls[0] == ["git", "rev-parse", "HEAD"]


def test_load_state_detects_deployment_and_local_vercel_link(tmp_path: Path) -> None:
    vercel_dir = tmp_path / ".vercel"
    vercel_dir.mkdir()
    (vercel_dir / "project.json").write_text("{}", encoding="utf-8")

    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return completed("def456\n")
        if "deployments" in command[2]:
            return completed('[{"environment":"Production"}]')
        if "check-runs" in command[2]:
            return completed('[{"name":"Vercel","app":{"slug":"vercel"}}]')
        raise AssertionError(f"unexpected command: {command}")

    state = load_deployment_state(repository="owner/repo", root=tmp_path, run=run)

    assert state.has_github_deployments
    assert state.has_vercel_check_runs
    assert state.vercel_project_linked
    assert state.is_deployed_to_vercel


def test_load_state_keeps_failed_github_queries_unknown(tmp_path: Path) -> None:
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return completed("abc123\n")
        if "deployments" in command[2]:
            return completed("gh auth failed", returncode=1)
        if "check-runs" in command[2]:
            return completed("not json")
        raise AssertionError(f"unexpected command: {command}")

    state = load_deployment_state(repository="owner/repo", root=tmp_path, run=run)
    summary = summarize_state(state)

    assert state.github_deployments.error == "command exited 1: gh auth failed"
    assert state.check_runs.error == "invalid JSON: Expecting value"
    assert not state.evidence_available
    assert "GitHub deployments: unknown (command exited 1: gh auth failed)" in summary
    assert "Vercel check-runs on commit: unknown (invalid JSON: Expecting value)" in summary
    assert "Verdict: unable to confirm deployment state" in summary


def test_summary_keeps_not_deployed_verdict_explicit() -> None:
    summary = summarize_state(
        DeploymentState(
            repository="owner/repo",
            commit="abc123",
            github_deployments=GitHubQuery(),
            check_runs=GitHubQuery(),
            vercel_project_linked=False,
            vercel_cli_available=False,
        )
    )

    assert "GitHub deployments: 0" in summary
    assert "Vercel check-runs on commit: no" in summary
    assert "Verdict: not deployed to Vercel yet" in summary
