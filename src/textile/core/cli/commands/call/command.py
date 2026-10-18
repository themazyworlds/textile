"""
Call Command Definition (`textile call`).
"""

import orjson
import typer

from textile.core.cli.commands.call.handler import execute_strand_call, parse_cli_args
from textile.core.cli.quill import quill
from textile.core.cli.ui import console


@quill.command("call")
def call_strand(
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
            console.print(f"[bold red]Error parsing JSON arguments:[/bold red] {e}")
            raise typer.Exit(code=1) from e
    elif args:
        parsed_kwargs = parse_cli_args(strand_name, args)

    execute_strand_call(strand_name, parsed_kwargs)
