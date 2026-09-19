"""
Textile Isolated Strand Subprocess Runner.
Invoked via `uv run --isolated` for ephemeral, dependency-isolated strand executions.
"""

import importlib
import json
import sys
from typing import Any


def main():
    if len(sys.argv) < 5:
        print(json.dumps({"success": False, "error": "Invalid arguments to isolated_runner"}))
        sys.exit(1)

    module_name = sys.argv[1]
    class_name = sys.argv[2]
    strand_name = sys.argv[3]
    args_json = sys.argv[4]

    try:
        args: dict[str, Any] = json.loads(args_json) if args_json else {}
    except Exception as e:
        print(json.dumps({"success": False, "error": f"Failed to parse arguments JSON: {e}"}))
        sys.exit(1)

    try:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        instance = cls()
        
        # Execute the raw handler or strand method directly
        res = instance._execute_direct(strand_name, args)
        print(json.dumps({"success": True, "result": res}))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
