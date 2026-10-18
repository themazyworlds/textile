"""
Skein Command Definition (`textile skein`).
"""

import typer

from textile.core.cli.commands.skein.handler import (
    handle_skein_disable,
    handle_skein_enable,
    handle_skein_toggle,
    render_skein_table,
    render_skein_tree,
)
from textile.core.cli.quill import quill
lazy from textile.core.orchestration.skein import skein


@quill.command("skein")
def cmd_skein(
    action: str | None = typer.Argument(None, help="enable, disable, toggle, tree"),
    yarn_target: str | None = typer.Argument(None, help="Target yarn name for enable/disable/toggle"),
):
    """Inspect and manage the Skein runtime layer hierarchy, policy engine, and yarn activation."""
    skein.initialize()

    if action == "enable" and yarn_target:
        handle_skein_enable(yarn_target)
    elif action == "disable" and yarn_target:
        handle_skein_disable(yarn_target)
    elif action == "toggle" and yarn_target:
        handle_skein_toggle(yarn_target)
    elif action == "tree":
        render_skein_tree()
    else:
        render_skein_table()
