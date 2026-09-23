"""
Textile Isolated Strand Subprocess Runner.
Invoked via `uv run --isolated` for ephemeral, dependency-isolated strand executions.
"""

import importlib
import json
import os
import sys
from typing import Any

from textile.core.sandbox import LandlockSandbox

MIN_ARG_COUNT = 5


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

    tier_name = sys.argv[5].upper() if len(sys.argv) > MIN_ARG_COUNT - 1 else ""

    try:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        instance = cls()

        # Apply kernel-level read-only walls for OBSERVE and INTERACT tiers
        if tier_name in ("OBSERVE", "INTERACT"):
            LandlockSandbox.apply_read_only()

        # Execute the raw handler or strand method directly
        res = instance._execute_direct(strand_name, args)
        print(json.dumps({"success": True, "result": res}))
        sys.exit(0)
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError, KeyError, OSError) as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
