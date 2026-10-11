"""
Textile Isolated Strand Subprocess Worker.
Executed in isolated subprocess / sandbox to execute a Yarn strand.
"""

import asyncio
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any

import orjson

MIN_WORKER_ARGS = 5
EXEC_EXCEPTIONS = (AttributeError, TypeError, ValueError, RuntimeError, ImportError, OSError)


def load_module(target_spec: str) -> Any:
    target_path = Path(target_spec).resolve()
    if target_spec.endswith(".py") or target_path.exists():
        if str(target_path.parent) not in sys.path:
            sys.path.insert(0, str(target_path.parent))
        mod_name = f"isolated_yarn_{target_path.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, str(target_path))
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load module spec: {target_spec}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        return mod
    return importlib.import_module(target_spec)


def main() -> None:
    if len(sys.argv) < MIN_WORKER_ARGS:
        sys.stdout.write(orjson.dumps({"success": False, "error": "Invalid worker arguments"}).decode() + "\n")
        sys.exit(1)

    target_spec, class_name, strand_name, args_json = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    try:
        args = orjson.loads(args_json) if args_json else {}
    except (orjson.JSONDecodeError, ValueError) as e:
        sys.stdout.write(
            orjson.dumps({"success": False, "error": f"Failed to parse arguments JSON: {e}"}).decode() + "\n"
        )
        sys.exit(1)

    try:
        mod = load_module(target_spec)
        cls = getattr(mod, class_name)
        instance = cls()

        target_fn = getattr(instance, strand_name, None)
        if target_fn is None:
            strands = getattr(instance, "get_strands", list)()
            matching = next((s for s in strands if getattr(s, "name", None) == strand_name), None)
            if matching:
                target_fn = getattr(matching, "raw_handler", None) or getattr(matching, "handler", None)

        if target_fn is None:
            raise AttributeError(f"Strand '{strand_name}' not found on '{class_name}'")

        sig = inspect.signature(target_fn)
        params = list(sig.parameters.values())
        if len(params) == 1 and params[0].name in ("args", "arguments", "params", "payload", "data"):
            res = target_fn(args)
        else:
            has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params)
            call_args = args if has_kwargs else {k: v for k, v in args.items() if k in sig.parameters}
            try:
                res = target_fn(**call_args)
            except TypeError:
                res = target_fn(args)

        if asyncio.iscoroutine(res) or inspect.isawaitable(res):
            res = asyncio.run(res)

        sys.stdout.write(orjson.dumps({"success": True, "result": res}).decode() + "\n")
        sys.exit(0)
    except EXEC_EXCEPTIONS as e:
        sys.stdout.write(orjson.dumps({"success": False, "error": str(e)}).decode() + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
