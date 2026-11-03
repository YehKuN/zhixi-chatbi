from __future__ import annotations

import sys
from pathlib import Path

import pytest
from agent_runtime.contracts import SandboxExecutionRequest, SandboxExecutionStatus
from application.local_sandbox import (
    LocalCommandCanceled,
    LocalCommandResult,
    LocalCommandTimedOut,
    LocalSandbox,
)
from application.script_workspace import ScriptWorkspaceManager


class FakeCancellation:
    def __init__(self, *, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


class FakeRunner:
    def __init__(self, *, result: LocalCommandResult | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def run(self, *, executable, work_dir, environment, timeout_seconds, cancellation):
        self.calls.append(
            {
                "executable": executable,
                "work_dir": work_dir,
                "environment": environment,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


async def _workspace(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("value\n1\n", encoding="utf-8")
    manager = ScriptWorkspaceManager(
        datasource_root=tmp_path / "sources",
        workspace_root=tmp_path / "workspaces",
        runtime_trace_root=tmp_path / "traces",
    )
    return manager, await manager.create(run_id="run_1", input_snapshot_path=str(source))


def _request(workspace_id: str) -> SandboxExecutionRequest:
    return SandboxExecutionRequest(
        workspace_id=workspace_id,
        command=("python", "analysis.py"),
        output_paths=["charts/chart.png"],
        purpose="analysis",
    )


@pytest.mark.asyncio
async def test_local_sandbox_completes_with_guard_environment(tmp_path) -> None:
    manager, workspace = await _workspace(tmp_path)
    await manager.write_analysis_script(workspace.workspace_id, "print('ok')")
    runner = FakeRunner(result=LocalCommandResult(exit_code=0, stdout="ok"))
    sandbox = LocalSandbox(
        workspaces=manager,
        python_executable=sys.executable,
        runner=runner,
    )

    result = await sandbox.execute(_request(workspace.workspace_id), FakeCancellation())

    assert result.status is SandboxExecutionStatus.COMPLETED
    call = runner.calls[0]
    environment = call["environment"]
    assert environment["MPLBACKEND"] == "Agg"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert Path(environment["MPLCONFIGDIR"]).is_dir()
    guard = Path(environment["PYTHONPATH"]) / "sitecustomize.py"
    assert guard.is_file()
    rc = Path(environment["MPLCONFIGDIR"]) / "matplotlibrc"
    assert "Microsoft YaHei" in rc.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_local_sandbox_rejects_unknown_command(tmp_path) -> None:
    manager, workspace = await _workspace(tmp_path)
    sandbox = LocalSandbox(workspaces=manager, python_executable=sys.executable)

    result = await sandbox.execute(
        _request(workspace.workspace_id).model_copy(update={"command": ("python", "other.py")}),
        FakeCancellation(),
    )

    assert result.status is SandboxExecutionStatus.REJECTED


@pytest.mark.asyncio
async def test_local_sandbox_reports_missing_interpreter(tmp_path) -> None:
    manager, workspace = await _workspace(tmp_path)
    await manager.write_analysis_script(workspace.workspace_id, "print('ok')")
    sandbox = LocalSandbox(
        workspaces=manager,
        python_executable=str(tmp_path / "missing-python"),
    )

    result = await sandbox.execute(_request(workspace.workspace_id), FakeCancellation())

    assert result.status is SandboxExecutionStatus.FAILED
    assert "解释器不可用" in result.failure.message


@pytest.mark.asyncio
async def test_local_sandbox_maps_child_timeout_and_cancel(tmp_path) -> None:
    manager, workspace = await _workspace(tmp_path)
    await manager.write_analysis_script(workspace.workspace_id, "print('ok')")

    timed_out = LocalSandbox(
        workspaces=manager,
        python_executable=sys.executable,
        runner=FakeRunner(error=LocalCommandTimedOut()),
    )
    result = await timed_out.execute(_request(workspace.workspace_id), FakeCancellation())
    assert result.status is SandboxExecutionStatus.TIMED_OUT

    canceled = LocalSandbox(
        workspaces=manager,
        python_executable=sys.executable,
        runner=FakeRunner(error=LocalCommandCanceled()),
    )
    result = await canceled.execute(_request(workspace.workspace_id), FakeCancellation())
    assert result.status is SandboxExecutionStatus.CANCELED


@pytest.mark.asyncio
async def test_local_sandbox_classifies_network_access(tmp_path) -> None:
    manager, workspace = await _workspace(tmp_path)
    await manager.write_analysis_script(workspace.workspace_id, "import socket")
    sandbox = LocalSandbox(
        workspaces=manager,
        python_executable=sys.executable,
        runner=FakeRunner(
            result=LocalCommandResult(
                exit_code=1,
                stderr='OSError: 本地沙箱已禁用网络访问',
            )
        ),
    )

    result = await sandbox.execute(_request(workspace.workspace_id), FakeCancellation())

    assert result.status is SandboxExecutionStatus.NETWORK_DENIED


@pytest.mark.asyncio
async def test_local_sandbox_returns_safe_diagnostic(tmp_path) -> None:
    manager, workspace = await _workspace(tmp_path)
    await manager.write_analysis_script(workspace.workspace_id, "x = 1\nraise ValueError('secret')")
    sandbox = LocalSandbox(
        workspaces=manager,
        python_executable=sys.executable,
        runner=FakeRunner(
            result=LocalCommandResult(
                exit_code=1,
                stderr='File "analysis.py", line 2, in <module>\nValueError: secret',
            )
        ),
    )

    result = await sandbox.execute(_request(workspace.workspace_id), FakeCancellation())

    assert result.status is SandboxExecutionStatus.FAILED
    assert result.diagnostic is not None
    assert result.diagnostic.exception_type == "ValueError"
    assert result.diagnostic.line_number == 2
    assert "secret" not in (result.diagnostic.message or "")
