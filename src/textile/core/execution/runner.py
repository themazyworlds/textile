"""
Textile Isolated Strand Subprocess Runner.
Invoked for dependency-isolated, sandbox-confined strand executions.
"""

import contextlib
import inspect
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson
from hem import (
    BubblewrapBuilder,
    CompletedProcess,
    TimeoutExpired,
    async_run_command,
    run_command,
)
from needle import CapabilityTier

from textile.core.definitions.errors import SandboxUnavailableError
from textile.core.security.policy import get_tier_policy
from textile.core.security.sandbox import create_sandbox_builder


def _format_handler_result(res: Any) -> str:
    """Format handler execution output into string or formatted JSON."""
    if isinstance(res, (dict, list)):
        return orjson.dumps(res, option=orjson.OPT_INDENT_2).decode()
    return str(res) if res is not None else "ok"


@dataclass(slots=True)
class _WorkerExecutionSpec:
    yarn: Any
    strand_name: str
    args: dict[str, Any]
    tier_str: str
    cwd: str


def _resolve_target_spec(yarn: Any) -> str:
    """Resolve target module spec or file path for isolated execution."""
    if hasattr(yarn, "_source_file") and yarn._source_file:
        return str(yarn._source_file)
    target_spec = yarn.__class__.__module__
    with contextlib.suppress(TypeError, OSError):
        file_path = inspect.getfile(yarn.__class__)
        if file_path and Path(file_path).exists():
            target_spec = file_path
    return target_spec


def _resolve_yarn_python(yarn: Any) -> str:
    """Resolve Python interpreter path for yarn, prioritizing yarn-local venv."""
    if hasattr(yarn, "_source_file") and yarn._source_file:
        p = Path(yarn._source_file).resolve()
        yarn_venv_py = p.parent / ".venv" / "bin" / "python"
        if yarn_venv_py.exists():
            return str(yarn_venv_py)
    with contextlib.suppress(TypeError, OSError, ValueError):
        file_path = inspect.getfile(yarn.__class__)
        if file_path:
            p = Path(file_path).resolve()
            yarn_venv_py = p.parent / ".venv" / "bin" / "python"
            if yarn_venv_py.exists():
                return str(yarn_venv_py)
    return sys.executable


def _build_worker_command(spec: _WorkerExecutionSpec) -> list[str]:
    """Construct isolated worker arguments."""
    target_spec = _resolve_target_spec(spec.yarn)
    python_bin = _resolve_yarn_python(spec.yarn)
    class_name = getattr(spec.yarn, "_class_name", spec.yarn.__class__.__name__)
    return [
        python_bin,
        "-m",
        "needle.worker",
        target_spec,
        class_name,
        spec.strand_name,
        orjson.dumps(spec.args).decode(),
        spec.tier_str,
    ]


def _prepare_execution(
    spec: _WorkerExecutionSpec,
    env: dict[str, str],
) -> tuple[BubblewrapBuilder | None, list[str]]:
    """Prepare sandbox builder or direct command according to tier policy."""
    raw_cmd = _build_worker_command(spec)
    policy = get_tier_policy(spec.tier_str)
    if policy.requires_sandbox:
        builder = create_sandbox_builder(
            raw_cmd,
            writable=policy.workspace_writable,
            env=env,
            workspace_root=spec.cwd,
            resources=getattr(spec.yarn, "resources", []),
        )
        return builder, raw_cmd
    return None, raw_cmd


def _parse_worker_output(res: CompletedProcess[str], strand_name: str) -> str:
    """Parse JSON stdout response from worker process."""
    out = res.stdout.strip()
    err = res.stderr.strip()
    if out:
        try:
            payload = orjson.loads(out)
            if payload.get("success"):
                return _format_handler_result(payload.get("result"))
            return f"Error: {payload.get('error', 'Execution failed')}"
        except orjson.JSONDecodeError, ValueError, TypeError:
            if res.returncode == 0:
                return out

    err_msg = err or out or f"Exit code {res.returncode}"
    return f"Error: Strand '{strand_name}' worker process crashed ({err_msg}). Host process preserved."


async def execute_strand_async(
    yarn: Any,
    strand_name: str,
    args: dict[str, Any],
    timeout: float | None = 300.0,
    tier: CapabilityTier | str = CapabilityTier.INTERACT,
) -> str:
    """Run a strand asynchronously in an isolated ephemeral process with sandbox confinement."""
    tier_str = tier.value if isinstance(tier, CapabilityTier) else str(tier)
    cwd = str(Path.cwd())
    spec = _WorkerExecutionSpec(
        yarn=yarn,
        strand_name=strand_name,
        args=args,
        tier_str=tier_str,
        cwd=cwd,
    )
    env = os.environ.copy()

    try:
        builder, raw_cmd = _prepare_execution(spec, env)
        proc_timeout = None if (timeout is None or timeout <= 0) else timeout
        if builder is not None:
            res = await builder.async_run(raw_cmd, capture_output=True, text=True, timeout=proc_timeout, env=env)
        else:
            res = await async_run_command(raw_cmd, capture_output=True, text=True, timeout=proc_timeout, env=env)
        return _parse_worker_output(res, strand_name)
    except TimeoutExpired, TimeoutError:
        return f"Error: Strand '{strand_name}' worker process timed out after {timeout} seconds."
    except SandboxUnavailableError as e:
        hint = f" (Hint: {e.hint})" if e.hint else ""
        return f"Error executing isolated strand '{strand_name}': {e.message}{hint}"
    except (OSError, ValueError) as e:
        return f"Error executing isolated strand '{strand_name}': {e}"


def execute_strand(
    yarn: Any,
    strand_name: str,
    args: dict[str, Any],
    timeout: float | None = 300.0,
    tier: CapabilityTier | str = CapabilityTier.INTERACT,
) -> str:
    """Run a strand synchronously in an isolated ephemeral process with sandbox confinement."""
    tier_str = tier.value if isinstance(tier, CapabilityTier) else str(tier)
    cwd = str(Path.cwd())
    spec = _WorkerExecutionSpec(
        yarn=yarn,
        strand_name=strand_name,
        args=args,
        tier_str=tier_str,
        cwd=cwd,
    )
    env = os.environ.copy()

    try:
        builder, raw_cmd = _prepare_execution(spec, env)
        proc_timeout = None if (timeout is None or timeout <= 0) else timeout
        if builder is not None:
            res = builder.run(raw_cmd, capture_output=True, text=True, timeout=proc_timeout, env=env)
        else:
            res = run_command(raw_cmd, capture_output=True, text=True, timeout=proc_timeout, env=env)
        return _parse_worker_output(res, strand_name)
    except TimeoutExpired, TimeoutError:
        return f"Error: Strand '{strand_name}' worker process timed out after {timeout} seconds."
    except SandboxUnavailableError as e:
        hint = f" (Hint: {e.hint})" if e.hint else ""
        return f"Error executing isolated strand '{strand_name}': {e.message}{hint}"
    except (OSError, ValueError) as e:
        return f"Error executing isolated strand '{strand_name}': {e}"
