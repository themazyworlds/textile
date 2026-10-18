"""
Authorize Command Definition (`textile authorize`).
"""

import typer

from textile.core.cli.commands.authorize.handler import handle_authorize
from textile.core.cli.quill import quill


@quill.command("authorize")
def cmd_authorize(
    code: bool = typer.Option(False, "--code", "-c", help="Generate and print current 6-digit TOTP code"),
):
    """Manage 2FA Authenticator (RFC 6238 TOTP) authorization credentials."""
    handle_authorize(code_only=code)
