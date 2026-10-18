"""
Textile CLI Strand and Yarn Execution Commands.
"""

import time
from typing import Any

import orjson
import typer
from needle.errors import StrandNotFoundError
lazy import pyotp

from textile.core.cli.quill import quill
from textile.core.cli.ui import Column, console, print_table
from textile.core.definitions.errors import TextileError
from textile.core.security.context import (
    OTPChallengeRequiredError,
    PolicyViolationError,
    get_totp_secret,
    get_totp_uri,
)
lazy from textile.core.orchestration import twill
lazy from textile.core.orchestration.loom import loom


def _parse_cli_args(strand_name: str, args: list[str]) -> dict[str, Any]:
    target = loom.get_strand(strand_name)
    param_names = list(target.parameters.keys()) if target and target.parameters else []
    kwargs: dict[str, Any] = {}
    pos_idx = 0

    for arg in args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            kwargs[k] = v.strip("\"'")
        elif pos_idx < len(param_names):
            kwargs[param_names[pos_idx]] = arg.strip("\"'")
            pos_idx += 1

    return kwargs


@quill.command("strands")
def list_strands(
    filter_query: str | None = typer.Argument(None, help="Optional filter string for strand names or descriptions"),
    tier: str | None = typer.Option(
        None,
        "--tier",
        "-t",
        help="Filter strands by capability tier (observe, interact, mutate, privileged, system_exec)",
    ),
):
    """List all registered and executable Textile Strands."""
    strands = loom.get_all_strands()
    query = (filter_query or "").strip().lower()

    matched: list[tuple[str, str, str]] = []
    for s in strands:
        s_name = s.name
        s_tier = str(s.tier or "")
        s_cap = s.capability or ""
        s_desc = (s.description or "").splitlines()[0].strip() if s.description else ""

        if query and query not in s_name.lower() and query not in s_desc.lower() and query not in s_cap.lower():
            continue
        if tier and tier.lower() != s_tier.lower():
            continue

        matched.append((s_name, s_tier, s_desc))

    print_table(
        header_title="Strands",
        columns=[
            Column("Strand", style="bold cyan", no_wrap=True),
            Column("Tier", style="dim", no_wrap=True),
            Column("Description", style="dim"),
        ],
        rows=matched,
    )


@quill.command("call")
def call_strand(
    strand_name: str = typer.Argument(
        ...,
        help="Name of the strand to execute",
    ),
    args: list[str] = typer.Argument(None, help="Key=Value parameters (e.g. text='Hello World' target=1)"),
    json_args: str | None = typer.Option(None, "--json", "-j", help="Raw JSON string of arguments"),
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
        parsed_kwargs = _parse_cli_args(strand_name, args)

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


@quill.command("inspect")
def inspect_strand(
    strand_name: str = typer.Argument(..., help="Name of strand to inspect parameter schema"),
):
    """Inspect detailed parameter schema and help for a specific strand."""
    target = loom.get_strand(strand_name)

    if not target:
        all_names = [s.name for s in loom.get_all_strands()]
        err = StrandNotFoundError(strand_name, available_strands=all_names)
        console.print(f"[bold red]{err.message}[/bold red]")
        console.print(f"[dim yellow]{err.hint}[/dim yellow]")
        raise typer.Exit(code=1)

    console.print(
        f"\n  [bold bright_cyan]Strand Details[/bold bright_cyan] [dim]•[/dim] [bold white]{target.name}[/bold white]\n"
    )
    console.print(f"  [bold white]Tier:[/bold white] {target.tier}")
    console.print(f"  [bold white]Description:[/bold white] {target.description or '—'}\n")

    if params := target.parameters or {}:
        rows = [
            (p_name, str(p_info.get("type", "any")), str(p_info.get("description", "")))
            for p_name, p_info in sorted(params.items())
        ]
        print_table(
            columns=[
                Column("Parameter", style="bold cyan"),
                Column("Type", style="green"),
                Column("Description", style="dim"),
            ],
            rows=rows,
        )


@quill.command("twill")
def cmd_twill():
    """Launch official Twill / MCP stdio server."""
    twill.run_twill()


@quill.command("2fa")
def cmd_2fa(
    code: bool = typer.Option(False, "--code", "-c", help="Generate and print current 6-digit TOTP code"),
):
    """Manage 2FA Authenticator (RFC 6238 TOTP)."""
    secret = get_totp_secret()
    if code:
        totp = pyotp.TOTP(secret)
        remaining = totp.interval - int(time.time()) % totp.interval
        console.print(
            f"\n  [bold cyan]Current Code:[/bold cyan] [bold bright_green]{totp.now()}[/bold bright_green] "
            f"[dim]({remaining}s remaining)[/dim]\n"
        )
        return

    uri = get_totp_uri(secret)
    console.print("\n  [bold bright_cyan]Textile 2FA Authenticator Setup (RFC 6238 TOTP)[/bold bright_cyan]\n")
    console.print(f"  [bold white]Secret Key:[/bold white] [bold yellow]{secret}[/bold yellow]")
    console.print(f"  [bold white]URI:[/bold white]        [dim]{uri}[/dim]")
    console.print("\n  [bold green]Usage with oathtool (offline):[/bold green]")
    console.print(f'  [cyan]oathtool --totp -b "{secret}"[/cyan]\n')
    console.print(
        "  [dim]Import this URI or secret key into Google Authenticator, "
        "Aegis, 1Password, Bitwarden, or YubiKey.[/dim]\n"
    )
