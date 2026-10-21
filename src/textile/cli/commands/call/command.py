"""
Call Command Definition (`quill call`).
"""

import typer
lazy import orjson
lazy from colorama.ansi import Fore, Style

from textile.cli.quill import quill
lazy from textile.cli.commands.call.handler import execute_strand_call, parse_cli_args


@quill.command("call")
async def call_strand(
    strand_name: str = typer.Argument(
        ...,
        help="Name of the strand to execute",
    ),
    args: list[str] = typer.Argument(None, help="Positional arguments passed to the strand in schema order"),
    json_args: str | None = typer.Option(None, "--json", "-j", help="Raw JSON string of arguments for complex schemas"),
):
    """Execute any registered Textile strand directly with parameter validation."""
    parsed_kwargs = {}

    if json_args:
        try:
            parsed_kwargs = orjson.loads(json_args)
        except orjson.JSONDecodeError as e:
            print(f"{Style.BRIGHT}{Fore.RED}Error parsing JSON arguments:{Style.RESET_ALL} {e}")
            raise typer.Exit(code=1) from e
    elif args:
        parsed_kwargs = parse_cli_args(strand_name, args)

    await execute_strand_call(strand_name, parsed_kwargs)
