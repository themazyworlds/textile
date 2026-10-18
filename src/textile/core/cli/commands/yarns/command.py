"""
Yarns Command Definition (`textile yarns`).
"""

from pathlib import Path

import platformdirs
import typer

from textile.core.cli.commands.yarns.handler import (
    handle_yarn_info,
    handle_yarn_install,
    handle_yarn_paths,
    handle_yarn_remove,
    render_yarns_list_table,
)
from textile.core.cli.quill import quill
lazy from textile.core.orchestration.skein import skein


@quill.command("yarns")
def cmd_yarns(
    action: str = typer.Argument("list", help="list, info, install, remove, paths"),
    target: str | None = typer.Argument(None, help="Yarn name, git repository URL, or local path"),
):
    """Manage installed capability yarns, inspection, and discovery search paths."""
    skein.initialize()
    user_yarns = Path(platformdirs.user_data_dir("textile")) / "yarns"

    if action in ("paths", "search-paths"):
        handle_yarn_paths()
    elif action == "info" and target:
        handle_yarn_info(target)
    elif action == "install" and target:
        handle_yarn_install(target, user_yarns)
    elif action == "remove" and target:
        handle_yarn_remove(target, user_yarns)
    else:
        render_yarns_list_table()
