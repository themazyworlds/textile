"""
Bubblewrap (bwrap) unprivileged container builder and isolation manager.
Enforces mount isolation, network namespaces, and capability tier bounds.
"""

import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from hem import BubblewrapBuilder

from textile.core.definitions.errors import SandboxUnavailableError
from textile.core.security.sandbox.resources import apply_sandbox_resources


def is_sandbox_available() -> bool:
    """Check if bubblewrap (bwrap) executable is present and working on the host."""
    return BubblewrapBuilder.is_available()


def _bind_user_config_and_share(builder: BubblewrapBuilder) -> None:
    """Bind user configuration (~/.config/textile) and local share (~/.local) into sandbox."""
    textile_config = Path.home() / ".config" / "textile"
    if textile_config.exists():
        builder.ro_bind(textile_config, try_ok=True)

    local_share = Path.home() / ".local"
    if local_share.exists():
        builder.ro_bind(local_share, try_ok=True)


def _requires_host_session(resources: Sequence[str] | None) -> bool:
    """Check if granted resources require preserving the host session/user namespace."""
    if not resources:
        return False
    session_indicators = ("dbus:session", "dbus-session", "display", "display:wayland")
    return any(
        str(r).lower() in session_indicators or str(r).lower().startswith("env:xdg_runtime_dir")
        for r in resources
    )


def create_sandbox_builder(
    cmd: Sequence[str],
    *,
    writable: bool = False,
    env: dict[str, str] | None = None,
    workspace_root: str | Path | None = None,
    resources: list[str] | None = None,
) -> BubblewrapBuilder:
    """Create and configure a BubblewrapBuilder sandbox container for cmd."""
    bwrap_path = shutil.which("bwrap")
    if not bwrap_path:
        raise SandboxUnavailableError("bwrap binary not found in system PATH.")

    ws = Path(workspace_root or Path.cwd()).resolve()
    allow_network = bool(resources and any("net" in str(r).lower() for r in resources))
    needs_host_session = _requires_host_session(resources)

    container_tmp = os.path.join("/", "tmp")
    container_home = os.path.join("/", "home")

    builder = (
        BubblewrapBuilder(bwrap_path)
        .clearenv()
        .bind_system_base()
        .bind_tmpfs_paths([container_tmp, container_home])
        .set_namespaces(allow_network=allow_network, unshare_user=not needs_host_session)
        .bind_workspace(ws, writable=writable)
        .set_standard_env(env)
        .bind_python_runtime()
        .bind_executable_dependencies(cmd)
        .bind_script_sources(cmd)
    )

    _bind_user_config_and_share(builder)

    if resources:
        apply_sandbox_resources(builder, resources)

    return builder


def wrap_sandboxed_command(
    cmd: list[str],
    *,
    writable: bool = False,
    env: dict[str, str] | None = None,
    workspace_root: str | Path | None = None,
    resources: list[str] | None = None,
) -> list[str]:
    """Wrap command in a bwrap sandbox container."""
    builder = create_sandbox_builder(
        cmd,
        writable=writable,
        env=env,
        workspace_root=workspace_root,
        resources=resources,
    )
    return builder.build(cmd)


class BubblewrapSandbox:
    """
    Linux Bubblewrap (bwrap) unprivileged container isolation manager.
    Enforces namespace isolation (mount, PID, IPC, network) and workspace confinement.
    """

    is_available = staticmethod(is_sandbox_available)
    create_builder = staticmethod(create_sandbox_builder)
    wrap_command = staticmethod(wrap_sandboxed_command)
