"""
Authorize Command Handler.
Manages RFC 6238 Time-Based One-Time Password (TOTP) 2FA credentials and terminal code generation.
"""

import time

lazy import pyotp

from textile.core.cli.ui import console
from textile.core.security.context import (
    get_totp_secret,
    get_totp_uri,
)


def handle_authorize(code_only: bool = False) -> None:
    """Generate TOTP verification code or print authenticator setup instructions."""
    secret = get_totp_secret()
    if code_only:
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
