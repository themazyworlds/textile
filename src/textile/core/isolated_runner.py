"""
Textile Isolated Strand Subprocess Runner.
Invoked via `uv run --isolated` for ephemeral, dependency-isolated strand executions.
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
from typing import Any

from textile.core.invoker import _format_handler_result
from textile.core.sandbox import BubblewrapSandbox, LandlockSandbox
from textile.core.strands import CapabilityTier

MIN_ARG_COUNT = 5


def execute_isolated_strand(
    yarn: Any,
    strand_name: str,
    args: dict[str, Any],
    timeout: float = 30.0,
    tier: CapabilityTier | str = CapabilityTier.INTERACT,
) -> str:
    """Run a strand in an isolated ephemeral subprocess using `uv`."""
    uv_bin = shutil.which("uv")
    if not uv_bin:
        return f"Error: `uv` binary required for isolated strand '{strand_name}' execution."

    tier_str = tier.value if isinstance(tier, CapabilityTier) else str(tier)
    cwd = os.getcwd()
    cmd = [uv_bin, "run", "--no-project", "--no-sync", "--quiet"]
    for dep in yarn.get_python_dependencies():
        cmd.extend(["--with", str(dep)])
    cmd.extend(
        [
            "-m",
            "textile.core.isolated_runner",
            yarn.__class__.__module__,
            yarn.__class__.__name__,
            strand_name,
            json.dumps(args),
            tier_str,
        ]
    )

    if BubblewrapSandbox.is_available() and tier_str.upper() != "PRIVILEGED":
        matching_strand = next((s for s in yarn.get_strands() if s.name == strand_name), None)
        res_list = matching_strand.resources if matching_strand else getattr(yarn.manifest, "resources", [])
        cmd = BubblewrapSandbox.wrap_command(cmd, tier=tier_str, workspace_root=cwd, resources=res_list)

    env = dict(os.environ)
    python_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{cwd}:{python_path}" if python_path else cwd

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False, env=env)
        out = res.stdout.strip()
        err = res.stderr.strip()
        if res.returncode == 0 and out:
            try:
                payload = json.loads(out)
                if payload.get("success"):
                    return _format_handler_result(payload.get("result"))
                return f"Error: {payload.get('error', 'Execution failed')}"
            except (json.JSONDecodeError, ValueError, TypeError):
                return out
        err_msg = err or f"Exit code {res.returncode}"
        return f"Error: Strand '{strand_name}' isolated worker process crashed ({err_msg}). Host process preserved."
    except subprocess.TimeoutExpired:
        return f"Error: Strand '{strand_name}' isolated worker process timed out after {timeout} seconds."
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        return f"Error executing isolated strand '{strand_name}': {e}"


def main():
    if len(sys.argv) < MIN_ARG_COUNT:
        print(json.dumps({"success": False, "error": "Invalid arguments to isolated_runner"}))
        sys.exit(1)

    module_name = sys.argv[1]
    class_name = sys.argv[2]
    strand_name = sys.argv[3]
    args_json = sys.argv[4]

    try:
        args: dict[str, Any] = json.loads(args_json) if args_json else {}
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(json.dumps({"success": False, "error": f"Failed to parse arguments JSON: {e}"}))
        sys.exit(1)

    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    tests_dir = os.path.join(cwd, "tests")
    if os.path.exists(tests_dir) and tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)

    tier_name = sys.argv[5].upper() if len(sys.argv) > MIN_ARG_COUNT else ""

    try:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        instance = cls()

        # Apply kernel-level read-only walls for OBSERVE and INTERACT tiers
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

        # Execute the raw handler or strand method directly
        res = instance._execute_direct(strand_name, args)
        print(json.dumps({"success": True, "result": res}))
        sys.exit(0)
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError, KeyError, OSError) as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
