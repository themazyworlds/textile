"""
Tapestry Command Definition (`quill tapestry`).
"""

import typer

from textile.cli.quill import quill
lazy from textile.cli.commands.tapestry.handler import handle_tapestry


@quill.command("tapestry")
def cmd_tapestry(
    json_output: bool = typer.Option(False, "--json", help="Output tapestry state as Pydantic JSON"),
):
    """Inspect engine task ledger and sensory blackboard."""
    handle_tapestry(json_output=json_output)
