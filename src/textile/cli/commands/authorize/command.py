"""
Authorize Command Definition (`quill authorize`).
"""

import typer

from textile.cli.quill import quill
lazy from textile.cli.commands.authorize.handler import handle_authorize


@quill.command("authorize")
def cmd_authorize(
    code: bool = typer.Option(False, "--code", "-c", help="Generate and print current 6-digit TOTP code"),
):
    """Manage 2FA Authenticator (RFC 6238 TOTP) authorization credentials."""
    handle_authorize(code_only=code)
