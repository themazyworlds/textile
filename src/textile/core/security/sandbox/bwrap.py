"""
Bubblewrap (bwrap) unprivileged container isolation for Textile strands.
Configures Hem sandbox with Textile configuration paths.
"""

from collections.abc import Sequence
from pathlib import Path

import hem
from hem import BubblewrapBuilder


def get_textile_config_binds() -> list[Path]:
    """Resolve user configuration (~/.config/textile) and local share (~/.local) paths."""
    binds: list[Path] = []
    textile_config = Path.home() / ".config" / "textile"
    if textile_config.exists():
        binds.append(textile_config)
    local_share = Path.home() / ".local"
    if local_share.exists():
        binds.append(local_share)
    return binds


def create_sandbox_builder(
    cmd: Sequence[str],
    *,
    writable: bool = False,
    env: dict[str, str] | None = None,
    workspace_root: str | Path | None = None,
    resources: Sequence[str] | None = None,
) -> BubblewrapBuilder:
    """Create and configure a BubblewrapBuilder sandbox container tailored for Textile strands."""
    return hem.create_sandbox(
        cmd,
        workspace=workspace_root,
        writable=writable,
        resources=resources,
        env=env,
        extra_ro_binds=get_textile_config_binds(),
    )
