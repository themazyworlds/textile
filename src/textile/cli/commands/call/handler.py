"""
Call Command Handler.
Executes strands dynamically via Loom with argument mapping and security policy enforcement.
"""

from typing import Any

import typer
lazy from colorama.ansi import Fore, Style

lazy from textile.core.camshaft import camshaft
lazy from textile.core.loom.mesh import loom


def parse_cli_args(strand_name: str, args: list[str]) -> dict[str, Any]:
    """Map positional CLI arguments to strand parameters by schema order."""
    target = loom.get_strand(strand_name)
    param_names = list(target.parameters.keys()) if target and target.parameters else []
    return dict(zip(param_names, args))


async def execute_strand_call(strand_name: str, parsed_kwargs: dict[str, Any]) -> None:
    """Execute target strand via Camshaft with visual OTP challenges and error formatting."""
    yarn = loom.get_yarn_for_strand(strand_name)
    yarn_name = yarn.name if yarn else "unknown"
    res = await camshaft.execute_strand(strand_name, parsed_kwargs)

    print(f"\n{res}")
    if str(res).startswith("Error:"):
        raise typer.Exit(code=1)

    if yarn_name != "unknown":
        banner = (
            f"\n{Style.DIM}sewn by{Style.RESET_ALL} "
            f"{Style.BRIGHT}{Fore.CYAN}{yarn_name}{Style.RESET_ALL} "
            f"{Style.DIM}>{Style.RESET_ALL} "
            f"{Style.BRIGHT}{Fore.WHITE}{strand_name}{Style.RESET_ALL}"
        )
        print(banner)
