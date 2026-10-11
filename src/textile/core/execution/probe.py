"""
Textile Yarn Schema Prober.
Executed in yarn's python environment to safely probe yarn metadata and strands.
"""

import importlib.util
import inspect
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import orjson

PROBE_PREFIX = "__TEXTILE_PROBE_JSON__:"
MIN_ARG_COUNT = 2
LOAD_EXCEPTIONS = (ImportError, SyntaxError, AttributeError, TypeError, ValueError, OSError, RuntimeError)


def load_module(target_path: Path) -> Any:
    if str(target_path.parent) not in sys.path:
        sys.path.insert(0, str(target_path.parent))
    mod_name = f"probed_yarn_{target_path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, str(target_path))
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
        return mod
    except LOAD_EXCEPTIONS:
        return None


def main() -> None:
    if len(sys.argv) < MIN_ARG_COUNT:
        sys.exit(0)

    target_path = Path(sys.argv[1]).resolve()
    mod = load_module(target_path)
    if not mod:
        sys.exit(0)

    mod_name = f"probed_yarn_{target_path.stem}"
    for name, attr in inspect.getmembers(mod, inspect.isclass):
        if name in ("Yarn", "ProbedYarn") or getattr(attr, "__module__", "") != mod_name:
            continue
        try:
            inst = attr()
        except LOAD_EXCEPTIONS:
            continue

        get_strands_fn = getattr(inst, "get_strands", None)
        raw_res = get_strands_fn() if callable(get_strands_fn) else []
        raw_strands: list[Any] = list(raw_res) if isinstance(raw_res, Iterable) else []
        strands_data: list[dict[str, Any]] = []
        for s in raw_strands:
            tier_obj = getattr(s, "tier", "interact")
            tier_val = getattr(tier_obj, "value", str(tier_obj))
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
        sys.stdout.write(f"{PROBE_PREFIX}{orjson.dumps(out).decode()}\n")


if __name__ == "__main__":
    main()
