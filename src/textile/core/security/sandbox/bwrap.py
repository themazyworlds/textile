"""
Bubblewrap (bwrap) unprivileged container builder and isolation manager.
Enforces mount isolation, network namespaces, and capability tier bounds.
"""

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from textile.core.definitions.errors import SandboxUnavailableError
from textile.core.security.sandbox.builder import BubblewrapBuilder
from textile.core.security.sandbox.resources import apply_sandbox_resources


def _bind_user_config_and_share(builder: BubblewrapBuilder) -> None:
    """Bind user configuration (~/.config/textile) and local share (~/.local) into sandbox."""
    textile_config = Path.home() / ".config" / "textile"
    if textile_config.exists():
        builder.ro_bind(textile_config, try_ok=True)

    local_share = Path.home() / ".local"
    if local_share.exists():
        builder.ro_bind(local_share, try_ok=True)


def _bind_python_prefixes(builder: BubblewrapBuilder) -> None:
    """Bind virtualenv, sys.prefix, and extra sys.path locations (e.g. editable packages) into sandbox."""
    for check_path in (sys.prefix, sys.base_prefix, getattr(sys, "base_exec_prefix", None)):
        if check_path and Path(check_path).exists():
            p_resolved = Path(check_path).resolve()
            p_str = str(p_resolved)
            if not any(p_str.startswith(prefix) for prefix in ("/usr", "/lib", "/opt", "/nix")):
                builder.ro_bind(p_resolved, try_ok=True)

    sys_temp = tempfile.gettempdir()
    ignored_prefixes = ("/usr", "/lib", "/opt", "/nix", sys_temp)
    for entry in sys.path:
        if entry and Path(entry).exists():
            p_res = Path(entry).resolve()
            p_str = str(p_res)
            if not any(p_str.startswith(prefix) for prefix in ignored_prefixes):
                target = p_res.parent if p_res.name == "src" else p_res
                builder.ro_bind(target, try_ok=True)


def _bind_executable_dependencies(builder: BubblewrapBuilder, cmd: list[str]) -> None:
    """Bind target executable path and containing venv directory into sandbox."""
    if not cmd or not cmd[0]:
        return
    exe_target = shutil.which(cmd[0]) or cmd[0]
    if Path(exe_target).exists():
        raw_path = str(Path(exe_target).absolute())
        resolved_path = str(Path(exe_target).resolve())
        for p_str in (raw_path, resolved_path):
            if ".venv" in p_str:
                venv_root = p_str.split("/bin/")[0]
                builder.ro_bind(venv_root, try_ok=True)
                # Bind any external source directories linked via .pth files (e.g. editable needle SDK)
                with contextlib.suppress(OSError):
                    for pth in Path(venv_root).glob("lib*/python*/site-packages/*.pth"):
                        for line in pth.read_text(encoding="utf-8").splitlines():
                            target_line = line.strip()
                            if target_line and not target_line.startswith(("#", "import ")):
                                p_pth = Path(target_line).resolve()
                                if p_pth.exists():
                                    bind_target = p_pth.parent if p_pth.name == "src" else p_pth
                                    builder.ro_bind(bind_target, try_ok=True)
            elif not any(p_str.startswith(prefix) for prefix in ("/usr", "/bin", "/lib", "/opt", "/nix")):
                parent_dir = Path(p_str).parent
                builder.ro_bind(parent_dir, try_ok=True)


class BubblewrapSandbox:
    """
    Linux Bubblewrap (bwrap) unprivileged container isolation manager.
    Enforces namespace isolation (mount, PID, IPC, network) and workspace confinement.
    """

    _AVAILABLE: bool | None = None

    @classmethod
    def is_available(cls) -> bool:
        """Check if bubblewrap (bwrap) executable is present and working."""
        if cls._AVAILABLE is not None:
            return cls._AVAILABLE
        if sys.platform != "linux":
            cls._AVAILABLE = False
            return False
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            cls._AVAILABLE = False
            return False
        try:
            res = subprocess.run(
                [bwrap_path, "--version"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            cls._AVAILABLE = res.returncode == 0
            return cls._AVAILABLE
        except OSError, subprocess.SubprocessError:
            cls._AVAILABLE = False
            return False

    @staticmethod
    def wrap_command(
        cmd: list[str],
        *,
        writable: bool = False,
        env: dict[str, str] | None = None,
        workspace_root: str | Path | None = None,
        resources: list[str] | None = None,
    ) -> list[str]:
        """Wrap command in a bwrap sandbox container."""
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            raise SandboxUnavailableError("bwrap binary not found in system PATH.")

        target_env = env if env is not None else dict(os.environ)
        is_writable = writable
        ws = Path(workspace_root or Path.cwd()).resolve()
        container_tmp = os.path.join("/", "tmp")
        container_home = os.path.join("/", "home")
        uv_cache = os.path.join(container_tmp, "uv_cache")

        allow_network = bool(resources and any("net" in str(r).lower() for r in resources))
        needs_host_session = bool(
            resources
            and any(
                str(r).lower() in ("dbus:session", "dbus-session", "display", "display:wayland")
                or str(r).lower().startswith("env:xdg_runtime_dir")
                for r in resources
            )
        )
        builder = (
            BubblewrapBuilder(bwrap_path)
            .clearenv()
            .bind_system_base()
            .bind_tmpfs_paths([container_tmp, container_home])
        )
        if resources:
            apply_sandbox_resources(builder, resources)

        (
            builder.set_namespaces(allow_network=allow_network, unshare_user=not needs_host_session)
            .bind_workspace(ws, writable=is_writable)
            .setenv("HOME", target_env.get("HOME", str(Path.home())))
            .setenv("USER", target_env.get("USER", os.getenv("USER", "user")))
            .setenv("PATH", target_env.get("PATH", "/usr/bin:/bin"))
            .setenv("UV_CACHE_DIR", uv_cache)
            .setenv("PYTHONPATH", target_env.get("PYTHONPATH"))
            .setenv("TERMINAL", target_env.get("TERMINAL"))
            .setenv("XDG_CONFIG_HOME", target_env.get("XDG_CONFIG_HOME"))
            .setenv("XDG_DATA_HOME", target_env.get("XDG_DATA_HOME"))
        )

        _bind_user_config_and_share(builder)
        _bind_python_prefixes(builder)
        _bind_executable_dependencies(builder, cmd)

        pythonpath = target_env.get("PYTHONPATH") or ""
        if pythonpath:
            for p in pythonpath.split(":"):
                if p and Path(p).exists():
                    p_res = str(Path(p).resolve())
                    builder.ro_bind(p_res, try_ok=True)

        for arg in cmd:
            if arg.endswith(".py") or Path(arg).exists():
                p_arg = Path(arg).resolve()
                builder.ro_bind(p_arg.parent, try_ok=True)

        return builder.build(cmd)
