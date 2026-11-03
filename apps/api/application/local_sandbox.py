"""无 Docker 环境下的本地 Python 沙箱（可信环境降级，不是强隔离）。

隔离能力弱于 Docker：只固定入口脚本、工作目录、超时和网络访问，
适合本机可信数据演示；生产环境仍应使用 DockerSandbox。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_runtime.contracts import (
    AgentErrorCode,
    AgentFailure,
    SandboxExecutionRequest,
    SandboxExecutionResult,
    SandboxExecutionStatus,
)
from agent_runtime.ports import CancellationSignal

from application.python_diagnostics import python_diagnostic
from application.script_workspace import (
    ScriptWorkspace,
    ScriptWorkspaceError,
    ScriptWorkspaceManager,
)

logger = logging.getLogger(__name__)

_NETWORK_DENIED_MARKERS = (
    "本地沙箱已禁用网络访问",
    "name or service not known",
    "temporary failure in name resolution",
)
_SECURITY_MARKERS = ("permission denied", "read-only file system", "access is denied")

_SITE_CUSTOMIZE = '''"""ChatBI 本地沙箱网络守卫；只作用于当前子进程。"""
import socket

_original_socket = socket.socket


class _DeniedSocket(_original_socket):
    def __init__(self, *args, **kwargs):
        raise OSError("本地沙箱已禁用网络访问")


def _deny_network(*args, **kwargs):
    raise OSError("本地沙箱已禁用网络访问")


socket.socket = _DeniedSocket
socket.create_connection = _deny_network
socket.getaddrinfo = _deny_network
'''

_MATPLOTLIB_RC = """font.family: sans-serif
font.sans-serif: Microsoft YaHei, SimHei, Noto Sans CJK JP, DejaVu Sans
axes.unicode_minus: False
"""


@dataclass(frozen=True)
class LocalCommandResult:
    """本地 Python 子进程的原始结果，不直接进入 Graph。"""

    exit_code: int
    stdout: str = ""
    stderr: str = ""


class LocalCommandTimedOut(TimeoutError):
    """本地 Python 子进程超过时限。"""


class LocalCommandCanceled(RuntimeError):
    """运行过程中收到取消信号。"""


class LocalPythonRunner(Protocol):
    """可替换的本地 Python 执行器，单元测试不需要真实子进程。"""

    async def run(
        self,
        *,
        executable: str,
        work_dir: Path,
        environment: dict[str, str],
        timeout_seconds: int,
        cancellation: CancellationSignal,
    ) -> LocalCommandResult: ...


class SubprocessPythonRunner:
    """用独立 Python 子进程执行 ``analysis.py``，超时或取消时终止进程树。"""

    async def run(
        self,
        *,
        executable: str,
        work_dir: Path,
        environment: dict[str, str],
        timeout_seconds: int,
        cancellation: CancellationSignal,
    ) -> LocalCommandResult:
        process = await asyncio.create_subprocess_exec(
            executable,
            "-s",
            "-B",
            "-u",
            "analysis.py",
            cwd=str(work_dir),
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        communicate = asyncio.create_task(process.communicate())
        deadline = time.monotonic() + timeout_seconds
        try:
            while not communicate.done():
                if cancellation.is_cancelled():
                    await self._terminate_tree(process)
                    raise LocalCommandCanceled
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await self._terminate_tree(process)
                    raise LocalCommandTimedOut
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(asyncio.shield(communicate), timeout=min(remaining, 0.1))
            stdout, stderr = await communicate
            return LocalCommandResult(
                exit_code=process.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace")[:8_000],
                stderr=stderr.decode("utf-8", errors="replace")[-16_384:],
            )
        finally:
            if not communicate.done():
                await self._terminate_tree(process)
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await communicate

    @staticmethod
    async def _terminate_tree(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        if os.name == "nt":
            with contextlib.suppress(OSError, asyncio.TimeoutError):
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/F",
                    "/T",
                    "/PID",
                    str(process.pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(killer.wait(), timeout=5)
        else:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()


class LocalSandbox:
    """SandboxPort 的本地实现；仅用于未安装 Docker 的可信开发环境。"""

    def __init__(
        self,
        *,
        workspaces: ScriptWorkspaceManager,
        python_executable: str,
        timeout_seconds: int = 30,
        timeout_provider: Callable[[], float] | None = None,
        runner: LocalPythonRunner | None = None,
    ) -> None:
        if not python_executable.strip():
            raise ValueError("Local sandbox python executable must be a non-empty path")
        if timeout_seconds <= 0:
            raise ValueError("Sandbox timeout must be positive")
        self.workspaces = workspaces
        self.python_executable = python_executable
        self.timeout_seconds = timeout_seconds
        self.timeout_provider = timeout_provider
        self.runner = runner or SubprocessPythonRunner()

    async def execute(
        self,
        request: SandboxExecutionRequest,
        cancellation: CancellationSignal,
    ) -> SandboxExecutionResult:
        started_at = time.perf_counter()
        if cancellation.is_cancelled():
            return self._canceled_result(started_at)
        if request.command != ("python", "analysis.py"):
            return self._rejected_result(started_at, "Sandbox 只允许执行固定分析脚本")
        try:
            workspace = self.workspaces.get(request.workspace_id)
        except ScriptWorkspaceError:
            return self._rejected_result(started_at, "Sandbox 工作区不可用")
        if not workspace.script_path.is_file() or workspace.script_path.is_symlink():
            return self._rejected_result(started_at, "分析脚本不可用")
        executable = self._resolve_executable()
        if executable is None:
            return self._failure_result(
                SandboxExecutionStatus.FAILED,
                AgentErrorCode.SANDBOX_FAILED,
                "本地沙箱解释器不可用，请先运行安装脚本准备 .venv-sandbox",
                started_at,
                retryable=False,
            )
        try:
            await self.workspaces.prepare_outputs(workspace.workspace_id, request.output_paths)
        except ScriptWorkspaceError:
            return self._rejected_result(started_at, "Sandbox 输出目录不可用")

        environment = self._prepare_environment(workspace)
        effective_timeout_seconds = float(self.timeout_seconds)
        if callable(self.timeout_provider):
            effective_timeout_seconds = min(
                effective_timeout_seconds, float(self.timeout_provider())
            )
        if effective_timeout_seconds < 1:
            return self._failure_result(
                SandboxExecutionStatus.TIMED_OUT,
                AgentErrorCode.SANDBOX_TIMEOUT,
                "分析脚本没有剩余 Run 时间",
                started_at,
            )
        effective_timeout = max(1, int(effective_timeout_seconds))
        try:
            result = await self.runner.run(
                executable=executable,
                work_dir=workspace.work_dir,
                environment=environment,
                timeout_seconds=effective_timeout,
                cancellation=cancellation,
            )
        except LocalCommandCanceled:
            return self._canceled_result(started_at)
        except LocalCommandTimedOut:
            return self._failure_result(
                SandboxExecutionStatus.TIMED_OUT,
                AgentErrorCode.SANDBOX_TIMEOUT,
                f"分析脚本运行超过 {effective_timeout} 秒限制",
                started_at,
            )
        except OSError:
            return self._failure_result(
                SandboxExecutionStatus.FAILED,
                AgentErrorCode.SANDBOX_FAILED,
                "本地 Sandbox 运行环境不可用",
                started_at,
                retryable=False,
            )
        except Exception:
            logger.warning("Local sandbox execution failed", exc_info=True)
            return self._failure_result(
                SandboxExecutionStatus.FAILED,
                AgentErrorCode.SANDBOX_FAILED,
                "本地 Sandbox 执行未完成，运行环境返回未知错误",
                started_at,
            )
        if cancellation.is_cancelled():
            return self._canceled_result(started_at)
        if result.exit_code == 0:
            return SandboxExecutionResult(
                status=SandboxExecutionStatus.COMPLETED,
                elapsed_ms=self._elapsed_ms(started_at),
                exit_code=0,
                stdout=result.stdout,
                stderr=result.stderr[-8_000:],
            )
        return self._classify_failed_command(result, started_at, workspace)

    def _resolve_executable(self) -> str | None:
        candidate = Path(self.python_executable).expanduser()
        if candidate.is_file():
            return str(candidate)
        located = shutil.which(self.python_executable)
        return located

    def _prepare_environment(self, workspace: ScriptWorkspace) -> dict[str, str]:
        tmp_dir = workspace.work_dir / ".sandbox-tmp"
        matplotlib_dir = tmp_dir / "matplotlib"
        guard_dir = tmp_dir / "guard"
        matplotlib_dir.mkdir(parents=True, exist_ok=True)
        guard_dir.mkdir(parents=True, exist_ok=True)
        (matplotlib_dir / "matplotlibrc").write_text(_MATPLOTLIB_RC, encoding="utf-8")
        (guard_dir / "sitecustomize.py").write_text(_SITE_CUSTOMIZE, encoding="utf-8")
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "SystemRoot": os.environ.get("SystemRoot", ""),
            "windir": os.environ.get("windir", ""),
            "COMSPEC": os.environ.get("COMSPEC", ""),
            "PATHEXT": os.environ.get("PATHEXT", ""),
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(matplotlib_dir),
            "HOME": str(workspace.work_dir),
            "USERPROFILE": str(workspace.work_dir),
            "TMP": str(tmp_dir),
            "TEMP": str(tmp_dir),
            "TMPDIR": str(tmp_dir),
            "PYTHONPATH": str(guard_dir),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        return {key: value for key, value in environment.items() if value}

    def _classify_failed_command(
        self,
        result: LocalCommandResult,
        started_at: float,
        workspace: ScriptWorkspace,
    ) -> SandboxExecutionResult:
        stderr = result.stderr
        lowered = stderr.lower()
        try:
            script = workspace.script_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            script = ""
        diagnostic = python_diagnostic(stderr, exit_code=result.exit_code, script=script)
        if any(marker in stderr or marker in lowered for marker in _NETWORK_DENIED_MARKERS):
            return self._failure_result(
                SandboxExecutionStatus.NETWORK_DENIED,
                AgentErrorCode.SANDBOX_NETWORK_DENIED,
                "分析脚本尝试访问网络，已被本地 Sandbox 阻止",
                started_at,
            )
        if diagnostic.exception_type == "PermissionError" or any(
            marker in lowered for marker in _SECURITY_MARKERS
        ):
            return self._rejected_result(started_at, "分析脚本触发了 Sandbox 安全限制")
        failure = self._failure_result(
            SandboxExecutionStatus.FAILED,
            AgentErrorCode.SANDBOX_FAILED,
            "分析脚本执行失败",
            started_at,
            retryable=result.exit_code == 1,
        )
        return failure.model_copy(
            update={
                "diagnostic": diagnostic,
                "exit_code": result.exit_code if 0 <= result.exit_code <= 255 else None,
            }
        )

    def _rejected_result(self, started_at: float, message: str) -> SandboxExecutionResult:
        return self._failure_result(
            SandboxExecutionStatus.REJECTED,
            AgentErrorCode.SANDBOX_REJECTED,
            message,
            started_at,
        )

    def _canceled_result(self, started_at: float) -> SandboxExecutionResult:
        return self._failure_result(
            SandboxExecutionStatus.CANCELED,
            AgentErrorCode.RUN_CANCELED,
            "分析已取消",
            started_at,
        )

    def _failure_result(
        self,
        status: SandboxExecutionStatus,
        code: AgentErrorCode,
        message: str,
        started_at: float,
        *,
        retryable: bool = False,
    ) -> SandboxExecutionResult:
        return SandboxExecutionResult(
            status=status,
            elapsed_ms=self._elapsed_ms(started_at),
            failure=AgentFailure(code=code, message=message, retryable=retryable),
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return max(0, round((time.perf_counter() - started_at) * 1000))
