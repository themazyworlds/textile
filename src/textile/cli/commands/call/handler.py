"""
Call Command Handler.
Executes strands dynamically via Loom with argument mapping and security policy enforcement.
"""

from typing import Any

import typer

from textile.cli.ui import console
from textile.core.definitions.errors import TextileError
from textile.core.security.context import (
    OTPChallengeRequiredError,
    PolicyViolationError,
)
lazy from textile.core.orchestration.loom import loom


def parse_cli_args(strand_name: str, args: list[str]) -> dict[str, Any]:
    """Map positional CLI arguments to strand parameters by schema order."""
    target = loom.get_strand(strand_name)
    param_names = list(target.parameters.keys()) if target and target.parameters else []
    return dict(zip(param_names, args))


def execute_strand_call(strand_name: str, parsed_kwargs: dict[str, Any]) -> None:
    """Execute target strand via Loom with visual OTP challenges and error formatting."""
    try:
        res = loom.execute_sync(strand_name, parsed_kwargs)
        console.print(res)
    except OTPChallengeRequiredError as e:
        console.print("\n  [bold bright_yellow]2FA Confirmation Required[/bold bright_yellow]")
        console.print("  [dim]Enter your 6-digit Authenticator / TOTP code to authorize this action.[/dim]")
        console.print(f"  [bold cyan]Confirm:[/bold cyan] textile call {strand_name} otp=<6_digit_code>\n")
        raise typer.Exit(code=1) from e
    except PolicyViolationError as e:
        console.print(f"\n  [bold red]Security Policy Violation:[/bold red] {e}\n")
        raise typer.Exit(code=1) from e
    except TextileError as e:
        console.print(f"[bold red]{e.message}[/bold red]")
        if e.hint:
            console.print(f"[dim yellow]Hint: {e.hint}[/dim yellow]")
        raise typer.Exit(code=1) from e
