"""
Textile Isolated Strand Subprocess Runner.
Invoked for dependency-isolated, sandbox-confined strand executions.
"""

import contextlib
import inspect
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson
from needle import CapabilityTier

from textile.core.definitions.errors import SandboxUnavailableError
from textile.core.security.sandbox import BubblewrapSandbox

MIN_ARG_COUNT = 5

_WORKER_SCRIPT = """
import sys, os, importlib.util, inspect, json, asyncio
from pathlib import Path

if len(sys.argv) < 5:
    print(json.dumps({"success": False, "error": "Invalid worker arguments"}))
    sys.exit(1)

target_spec, class_name, strand_name, args_json = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

try:
    args = json.loads(args_json) if args_json else {}
except Exception as e:
    print(json.dumps({"success": False, "error": f"Failed to parse arguments JSON: {e}"}))
    sys.exit(1)

try:
    if target_spec.endswith(".py") or Path(target_spec).exists():
        p = Path(target_spec).resolve()
        if str(p.parent) not in sys.path:
            sys.path.insert(0, str(p.parent))
        mod_name = f"isolated_yarn_{p.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, str(p))
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load module spec: {target_spec}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(target_spec)

    cls = getattr(mod, class_name)
    instance = cls()

    target_fn = getattr(instance, strand_name, None)
    if target_fn is None:
        strands = getattr(instance, "get_strands", lambda: [])()
        matching = next((s for s in strands if getattr(s, "name", None) == strand_name), None)
        if matching and getattr(matching, "raw_handler", None):
            target_fn = matching.raw_handler
        elif matching and getattr(matching, "handler", None):
            target_fn = matching.handler

    if target_fn is None:
        raise AttributeError(f"Strand '{strand_name}' not found on '{class_name}'")

    sig = inspect.signature(target_fn)
    params = list(sig.parameters.values())
    if len(params) == 1 and params[0].name in ("args", "arguments", "params", "payload", "data"):
        res = target_fn(args)
    else:
        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
        if has_kwargs:
            call_args = args
        else:
            call_args = {k: v for k, v in args.items() if k in sig.parameters}
        try:
            res = target_fn(**call_args)
        except TypeError:
            res = target_fn(args)

    if asyncio.iscoroutine(res) or inspect.isawaitable(res):
        res = asyncio.run(res)

    print(json.dumps({"success": True, "result": res}))
    sys.exit(0)
except Exception as e:
    print(json.dumps({"success": False, "error": str(e)}))
    sys.exit(1)
"""

_PROBE_SCRIPT = """
import sys, os, importlib.util, inspect, json
from pathlib import Path

target_path = Path(sys.argv[1]).resolve()
if str(target_path.parent) not in sys.path:
    sys.path.insert(0, str(target_path.parent))

mod_name = f"probed_yarn_{target_path.stem}"
spec = importlib.util.spec_from_file_location(mod_name, str(target_path))
if not spec or not spec.loader:
    sys.exit(0)

mod = importlib.util.module_from_spec(spec)
sys.modules[mod_name] = mod
try:
    spec.loader.exec_module(mod)
except Exception:
    pass

type_map = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

for name, attr in inspect.getmembers(mod, inspect.isclass):
    if name not in ("Yarn", "ProbedYarn") and getattr(attr, "__module__", "") == mod_name:
        try:
            inst = attr()
        except Exception:
            continue

        strands_data = []
        get_strands = getattr(inst, "get_strands", None)
        if callable(get_strands):
            try:
                raw_strands = get_strands()
            except Exception:
                raw_strands = []
        else:
            raw_strands = []

        if raw_strands:
            for s in raw_strands:
                tier_val = getattr(s, "tier", "interact")
                if hasattr(tier_val, "value"):
                    tier_val = tier_val.value
                s_no_timeout = bool(getattr(s, "no_timeout", False))
                s_timeout = None if s_no_timeout else getattr(s, "timeout", None)
                strands_data.append({
                    "name": getattr(s, "name", ""),
                    "description": getattr(s, "description", getattr(s, "name", "")),
                    "tier": str(tier_val),
                    "parameters": getattr(s, "parameters", {}),
                    "required": getattr(s, "required", []),
                    "resources": list(getattr(s, "resources", [])),
                    "timeout": s_timeout,
                    "no_timeout": s_no_timeout,
                })
        else:
            for m_name in dir(attr):
                if m_name.startswith("__") or m_name in ("is_available", "get_strands", "build_strand"):
                    continue
                m_val = getattr(attr, m_name, None)
                if callable(m_val) and (getattr(m_val, "_is_strand", False) or not m_name.startswith("_")):
                    s_name = getattr(m_val, "_strand_name", m_name)
                    s_desc = getattr(m_val, "_strand_description", None) or inspect.getdoc(m_val) or s_name
                    is_priv = s_name.startswith(("run_", "launch_", "exec_"))
                    default_tier = "privileged" if is_priv else "interact"
                    s_tier = getattr(m_val, "_strand_tier", default_tier)
                    if hasattr(s_tier, "value"):
                        s_tier = s_tier.value
                    s_no_timeout = bool(getattr(m_val, "_strand_no_timeout", False))
                    s_timeout = None if s_no_timeout else getattr(m_val, "_strand_timeout", None)
                    sig = inspect.signature(m_val)
                    props = {}
                    req = []
                    for p_name, p in sig.parameters.items():
                        if p_name in ("self", "cls"):
                            continue
                        p_type = "string"
                        if p.annotation is not inspect.Parameter.empty:
                            p_type = type_map.get(p.annotation, "string")
                        prop = {"type": p_type}
                        if p.default is not inspect.Parameter.empty:
                            prop["default"] = p.default
                        else:
                            req.append(p_name)
                        props[p_name] = prop

                    strands_data.append({
                        "name": s_name,
                        "description": s_desc.splitlines()[0].strip() if s_desc else s_name,
                        "tier": str(s_tier),
                        "parameters": props,
                        "required": req,
                        "resources": list(getattr(inst, "resources", [])),
                        "timeout": s_timeout,
                        "no_timeout": s_no_timeout,
                    })

        doc_desc = (attr.__doc__ or "").strip().splitlines()[0] if attr.__doc__ else name
        out = {
            "class_name": name,
            "name": getattr(inst, "name", name.lower().removesuffix("yarn")),
            "description": getattr(inst, "description", doc_desc),
            "layer": getattr(inst, "layer", 150),
            "tailor": getattr(inst, "tailor", "textile"),
            "version": getattr(inst, "version", "1.0.0"),
            "resources": list(getattr(inst, "resources", [])),
            "strands": strands_data,
        }
        print("__TEXTILE_PROBE_JSON__:" + json.dumps(out))
"""


def _format_handler_result(res: Any) -> str:
    """Format handler execution output into string or formatted JSON."""
    if isinstance(res, (dict, list)):
        return orjson.dumps(res, option=orjson.OPT_INDENT_2).decode()
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


def _build_worker_command(spec: _WorkerExecutionSpec, env: dict[str, str] | None = None) -> list[str]:
    """Construct isolated subprocess command with sandbox wrapping if applicable."""
    target_spec = _resolve_target_spec(spec.yarn)
    python_bin = _resolve_yarn_python(spec.yarn)
    class_name = getattr(spec.yarn, "_class_name", spec.yarn.__class__.__name__)
    cmd = [
        python_bin,
        "-c",
        _WORKER_SCRIPT,
        target_spec,
        class_name,
        spec.strand_name,
        orjson.dumps(spec.args).decode(),
        spec.tier_str,
    ]

    if spec.tier_str.upper() != "PRIVILEGED":
        if not BubblewrapSandbox.is_available():
            raise SandboxUnavailableError(
                "Bubblewrap ('bwrap') is not installed or operational on this system. "
                "Sandboxed strands require bubblewrap for isolation."
            )
        matching_strand = next((s for s in spec.yarn.get_strands() if s.name == spec.strand_name), None)
        res_list = matching_strand.resources if matching_strand else getattr(spec.yarn, "resources", [])
        cmd = BubblewrapSandbox.wrap_command(
            cmd, tier=spec.tier_str, env=env, workspace_root=spec.cwd, resources=res_list
        )

    return cmd


def _parse_worker_output(res: subprocess.CompletedProcess[str], strand_name: str) -> str:
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


def execute_strand(
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

    try:
        cmd = _build_worker_command(spec, env=env)
        proc_timeout = None if (timeout is None or timeout <= 0) else timeout
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=proc_timeout, check=False, env=env)
        return _parse_worker_output(res, strand_name)
    except subprocess.TimeoutExpired:
        return f"Error: Strand '{strand_name}' worker process timed out after {timeout} seconds."
    except SandboxUnavailableError as e:
        hint = f" (Hint: {e.hint})" if e.hint else ""
        return f"Error executing isolated strand '{strand_name}': {e.message}{hint}"
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        return f"Error executing isolated strand '{strand_name}': {e}"
