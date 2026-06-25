import subprocess
from collections.abc import Sequence
from pathlib import Path

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.infra.bootstrap import (
    LOCAL_SERVICES,
    apply_local_bootstrap,
    local_bootstrap_command,
    local_bootstrap_summary,
)


def test_local_bootstrap_summary_reports_compose_assets() -> None:
    summary = local_bootstrap_summary()

    assert summary.compose_file == "infra/docker-compose.yml"
    assert summary.services == LOCAL_SERVICES
    assert summary.command == local_bootstrap_command()
    assert summary.topic_count > 0
    assert "cypher/migrations/0001_constraints.cypher" in summary.cypher_migrations


def test_apply_local_bootstrap_runs_compose_command() -> None:
    calls: list[tuple[Sequence[str], Path, float]] = []

    def runner(
        args: Sequence[str],
        *,
        cwd: Path,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((args, cwd, timeout))
        return subprocess.CompletedProcess(
            args=list(args),
            returncode=0,
            stdout="started\n",
            stderr="",
        )

    result = apply_local_bootstrap(timeout_seconds=12, runner=runner)

    assert result.status == "started"
    assert result.returncode == 0
    assert result.stdout == "started\n"
    assert result.summary.apply is True
    assert calls == [(local_bootstrap_command(), Path.cwd(), 12)]


def test_apply_local_bootstrap_reports_failure_without_raising() -> None:
    def runner(
        args: Sequence[str],
        *,
        cwd: Path,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, text, capture_output, check, timeout
        return subprocess.CompletedProcess(
            args=list(args),
            returncode=1,
            stdout="",
            stderr="pull failed\n",
        )

    result = apply_local_bootstrap(runner=runner)

    assert result.status == "failed"
    assert result.returncode == 1
    assert result.stderr == "pull failed\n"


def test_bootstrap_infra_apply_is_local_only() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["bootstrap-infra", "--mode", "hybrid", "--apply"])

    assert result.exit_code != 0
    assert "--mode local" in result.output
