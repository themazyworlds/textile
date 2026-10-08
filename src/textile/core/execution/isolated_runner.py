"""
Textile Isolated Strand Subprocess Runner.
Invoked via `uv run --isolated` for ephemeral, dependency-isolated strand executions.
"""

import contextlib
import importlib
import importlib.util
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import textile
from textile.core.definitions.errors import SandboxUnavailableError
from textile.core.execution.invoker import execute_direct
from textile.core.execution.strands import CapabilityTier
from textile.core.security.sandbox import BubblewrapSandbox, LandlockSandbox

MIN_ARG_COUNT = 5


def _format_handler_result(res: Any) -> str:
    """Format handler execution output into string or formatted JSON."""
    if isinstance(res, (dict, list)):
        return json.dumps(res, indent=2)
    return str(res) if res is not None else "ok"


@dataclass(slots=True)
class _WorkerExecutionSpec:
    uv_bin: str
    yarn: Any
    strand_name: str
    args: dict[str, Any]
    tier_str: str
    cwd: str


def _resolve_target_spec(yarn: Any) -> str:
    """Resolve target module spec or file path for isolated execution."""
    target_spec = yarn.__class__.__module__
    with contextlib.suppress(TypeError, OSError):
        file_path = inspect.getfile(yarn.__class__)
        if file_path and Path(file_path).exists():
            target_spec = file_path
    return target_spec


def _build_worker_command(spec: _WorkerExecutionSpec, env: dict[str, str] | None = None) -> list[str]:
    """Construct isolated subprocess command with sandbox wrapping if applicable."""
    target_spec = _resolve_target_spec(spec.yarn)
    cmd = [
        sys.executable,
        "-c",
        "from textile.core.execution.isolated_runner import main; main()",
        target_spec,
        spec.yarn.__class__.__name__,
        spec.strand_name,
        json.dumps(spec.args),
        spec.tier_str,
    ]

    if BubblewrapSandbox.is_available() and spec.tier_str.upper() != "PRIVILEGED":
        matching_strand = next((s for s in spec.yarn.get_strands() if s.name == spec.strand_name), None)
        res_list = matching_strand.resources if matching_strand else getattr(spec.yarn, "resources", [])
        cmd = BubblewrapSandbox.wrap_command(
            cmd, tier=spec.tier_str, env=env, workspace_root=spec.cwd, resources=res_list
        )

    return cmd


def _parse_worker_output(res: subprocess.CompletedProcess[str], strand_name: str) -> str:
    """Parse JSON stdout response from isolated worker process."""
    out = res.stdout.strip()
    err = res.stderr.strip()
    if out:
        try:
            payload = json.loads(out)
            if payload.get("success"):
                return _format_handler_result(payload.get("result"))
            return f"Error: {payload.get('error', 'Execution failed')}"
        except (json.JSONDecodeError, ValueError, TypeError):
            if res.returncode == 0:
                return out

    err_msg = err or out or f"Exit code {res.returncode}"
    return f"Error: Strand '{strand_name}' isolated worker process crashed ({err_msg}). Host process preserved."


def _build_isolated_pythonpath(yarn: Any, cwd: str, existing_pythonpath: str = "") -> str:
    """Build unified PYTHONPATH containing textile root, yarn paths, and site-packages."""
    textile_pkg_dir = str(Path(textile.__file__).resolve().parent.parent)
    paths_to_add = [textile_pkg_dir, cwd]
    for p in sys.path:
        if p and "site-packages" in p and p not in paths_to_add:
            paths_to_add.append(p)

    with contextlib.suppress(Exception):
        file_path = inspect.getfile(yarn.__class__)
        if file_path:
            p = Path(file_path).resolve()
            paths_to_add.extend([str(p.parent), str(p.parent.parent)])
            curr = p.parent
            while curr != curr.parent:
                venv_sp = curr / ".venv" / "lib"
                if venv_sp.exists():
                    for sp in venv_sp.glob("python*/site-packages"):
                        paths_to_add.append(str(sp))
                    break
                curr = curr.parent

    all_paths = [p for p in paths_to_add if p]
    if existing_pythonpath:
        for p in existing_pythonpath.split(":"):
            if p and p not in all_paths:
                all_paths.append(p)
    return ":".join(all_paths)


def execute_isolated_strand(
    yarn: Any,
    strand_name: str,
    args: dict[str, Any],
    timeout: float | None = 300.0,
    tier: CapabilityTier | str = CapabilityTier.INTERACT,
) -> str:
    """Run a strand in an isolated ephemeral subprocess with sandbox confinement."""
    uv_bin = shutil.which("uv") or sys.executable

    tier_str = tier.value if isinstance(tier, CapabilityTier) else str(tier)
    cwd = str(Path.cwd())
    spec = _WorkerExecutionSpec(
        uv_bin=uv_bin,
        yarn=yarn,
        strand_name=strand_name,
        args=args,
        tier_str=tier_str,
        cwd=cwd,
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = _build_isolated_pythonpath(yarn, cwd, env.get("PYTHONPATH", ""))

    try:
        cmd = _build_worker_command(spec, env=env)
        proc_timeout = None if (timeout is None or timeout <= 0) else timeout
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=proc_timeout, check=False, env=env)
        return _parse_worker_output(res, strand_name)
    except subprocess.TimeoutExpired:
        return f"Error: Strand '{strand_name}' isolated worker process timed out after {timeout} seconds."
    except SandboxUnavailableError as e:
        return f"Error executing isolated strand '{strand_name}': {e.message}"
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        return f"Error executing isolated strand '{strand_name}': {e}"


def _load_target_module(target_spec: str) -> Any:
    """Load module dynamically from file location or package import."""
    if target_spec.endswith(".py") or Path(target_spec).exists():
        mod_name = f"isolated_yarn_{Path(target_spec).stem}"
        spec = importlib.util.spec_from_file_location(mod_name, target_spec)
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load module spec from file location: {target_spec}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$", target_spec):
        raise ValueError(f"Invalid target module specification: {target_spec}")
    spec = importlib.util.find_spec(target_spec)
    if not spec or not spec.loader:
        raise ImportError(f"Cannot find module spec for: {target_spec}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[target_spec] = mod
    spec.loader.exec_module(mod)
    return mod


def _setup_worker_sys_path() -> None:
    """Ensure working directory and tests directory exist in sys.path."""
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    tests_dir = Path(cwd) / "tests"
    if tests_dir.exists() and str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))


def main():
    if len(sys.argv) < MIN_ARG_COUNT:
        print(json.dumps({"success": False, "error": "Invalid arguments to isolated_runner"}))
        sys.exit(1)

    target_spec = sys.argv[1]
    class_name = sys.argv[2]
    strand_name = sys.argv[3]
    args_json = sys.argv[4]

    try:
        args: dict[str, Any] = json.loads(args_json) if args_json else {}
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(json.dumps({"success": False, "error": f"Failed to parse arguments JSON: {e}"}))
        sys.exit(1)

    _setup_worker_sys_path()
    tier_name = sys.argv[5].upper() if len(sys.argv) > MIN_ARG_COUNT else ""

    try:
        mod = _load_target_module(target_spec)
        cls = getattr(mod, class_name)
        instance = cls()

        if (
            tier_name in ("OBSERVE", "INTERACT")
            and LandlockSandbox.is_supported()
            and not LandlockSandbox.apply_read_only()
        ):
            print(
                json.dumps(
                    {"success": False, "error": f"Failed to apply Landlock read-only sandbox for tier {tier_name}"}
                )
            )
            sys.exit(1)

        res = execute_direct(instance, strand_name, args)
        print(json.dumps({"success": True, "result": res}))
        sys.exit(0)
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError, KeyError, OSError) as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()

