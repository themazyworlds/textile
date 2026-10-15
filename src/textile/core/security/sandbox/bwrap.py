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
from textile.core.security.sandbox.resources import resolve_sandbox_resources


class BubblewrapBuilder:
    """Builder pattern for constructing Bubblewrap (bwrap) execution arguments cleanly."""

    def __init__(self, bwrap_path: str):
        self.args: list[str] = [bwrap_path, "--clearenv"]

    def bind_system_base(self) -> BubblewrapBuilder:
        self.args.extend(["--ro-bind", "/usr", "/usr"])
        lib64_target = "usr/lib64" if Path("/usr/lib64").exists() else "usr/lib"
        self.args.extend(
            [
                "--symlink",
                lib64_target,
                "/lib64",
                "--symlink",
                "usr/lib",
                "/lib",
                "--symlink",
                "usr/bin",
                "/bin",
                "--symlink",
                "usr/bin",
                "/sbin",
            ]
        )

        for p in ("/etc", "/sys", "/opt", "/nix"):
            self.args.extend(["--ro-bind-try", p, p])
        self.args.extend(["--dev", "/dev", "--proc", "/proc"])
        return self

    def bind_tmpfs(self, paths: list[str]) -> BubblewrapBuilder:
        for p in paths:
            self.args.extend(["--tmpfs", p])
        return self

    def set_namespaces(self, allow_network: bool, unshare_user: bool = True) -> BubblewrapBuilder:
        if unshare_user:
            self.args.extend(["--unshare-user", "--unshare-pid"])
        self.args.extend(["--unshare-ipc", "--unshare-uts", "--die-with-parent"])
        if not allow_network:
            self.args.append("--unshare-net")
        return self

    def bind_resources(self, resources: list[str] | None) -> BubblewrapBuilder:
        if resources:
            self.args.extend(resolve_sandbox_resources(resources))
        return self

    def bind_workspace(self, workspace: Path, writable: bool) -> BubblewrapBuilder:
        flag = "--bind" if writable else "--ro-bind"
        self.args.extend([flag, str(workspace), str(workspace), "--chdir", str(workspace)])
        return self

    def set_env(self, key: str, val: str | None) -> BubblewrapBuilder:
        if val:
            self.args.extend(["--setenv", key, val])
        return self

    def build(self, target_cmd: list[str]) -> list[str]:
        return self.args + target_cmd


def _bind_user_config_and_share(builder: BubblewrapBuilder) -> None:
    """Bind user configuration (~/.config/textile) and local share (~/.local) into sandbox."""
    textile_config = Path.home() / ".config" / "textile"
    if textile_config.exists():
        builder.args.extend(["--ro-bind-try", str(textile_config), str(textile_config)])

    local_share = Path.home() / ".local"
    if local_share.exists():
        builder.args.extend(["--ro-bind-try", str(local_share), str(local_share)])


def _bind_python_prefixes(builder: BubblewrapBuilder) -> None:
    """Bind virtualenv, sys.prefix, and extra sys.path locations (e.g. editable packages) into sandbox."""
    for check_path in (sys.prefix, sys.base_prefix, getattr(sys, "base_exec_prefix", None)):
        if check_path and Path(check_path).exists():
            p_resolved = str(Path(check_path).resolve())
            if not any(p_resolved.startswith(prefix) for prefix in ("/usr", "/lib", "/opt", "/nix")):
                builder.args.extend(["--ro-bind-try", p_resolved, p_resolved])

    sys_temp = tempfile.gettempdir()
    ignored_prefixes = ("/usr", "/lib", "/opt", "/nix", sys_temp)
    for entry in sys.path:
        if entry and Path(entry).exists():
            p_res = Path(entry).resolve()
            p_str = str(p_res)
            if not any(p_str.startswith(prefix) for prefix in ignored_prefixes):
                target = str(p_res.parent if p_res.name == "src" else p_res)
                builder.args.extend(["--ro-bind-try", target, target])


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
                builder.args.extend(["--ro-bind-try", venv_root, venv_root])
                # Bind any external source directories linked via .pth files (e.g. editable needle SDK)
                with contextlib.suppress(OSError):
                    for pth in Path(venv_root).glob("lib*/python*/site-packages/*.pth"):
                        for line in pth.read_text(encoding="utf-8").splitlines():
                            target_line = line.strip()
                            if target_line and not target_line.startswith(("#", "import ")):
                                p_pth = Path(target_line).resolve()
                                if p_pth.exists():
                                    bind_target = str(p_pth.parent if p_pth.name == "src" else p_pth)
                                    builder.args.extend(["--ro-bind-try", bind_target, bind_target])
            elif not any(p_str.startswith(prefix) for prefix in ("/usr", "/bin", "/lib", "/opt", "/nix")):
                parent_dir = str(Path(p_str).parent)
                builder.args.extend(["--ro-bind-try", parent_dir, parent_dir])


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
        tier: str,
        *,
        env: dict[str, str] | None = None,
        workspace_root: str | Path | None = None,
        resources: list[str] | None = None,
    ) -> list[str]:
        """Wrap command in a bwrap sandbox container tailored to the capability tier."""
        bwrap_path = shutil.which("bwrap")
        tier_upper = tier.upper()
        if "PRIVILEGED" in tier_upper:
            return cmd

        if not bwrap_path:
            raise SandboxUnavailableError("bwrap binary not found in system PATH.")

        target_env = env if env is not None else dict(os.environ)
        is_writable = "MUTATE" in tier_upper
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
            .bind_system_base()
            .bind_tmpfs([container_tmp, container_home])
            .bind_resources(resources)
            .set_namespaces(allow_network=allow_network, unshare_user=not needs_host_session)
            .bind_workspace(ws, is_writable)
            .set_env("HOME", target_env.get("HOME", str(Path.home())))
            .set_env("USER", target_env.get("USER", os.getenv("USER", "user")))
            .set_env("PATH", target_env.get("PATH", "/usr/bin:/bin"))
            .set_env("UV_CACHE_DIR", uv_cache)
            .set_env("PYTHONPATH", target_env.get("PYTHONPATH"))
            .set_env("TERMINAL", target_env.get("TERMINAL"))
            .set_env("XDG_CONFIG_HOME", target_env.get("XDG_CONFIG_HOME"))
            .set_env("XDG_DATA_HOME", target_env.get("XDG_DATA_HOME"))
        )

        _bind_user_config_and_share(builder)
        _bind_python_prefixes(builder)
        _bind_executable_dependencies(builder, cmd)

        pythonpath = target_env.get("PYTHONPATH") or ""
        if pythonpath:
            for p in pythonpath.split(":"):
                if p and Path(p).exists():
                    p_res = str(Path(p).resolve())
                    builder.args.extend(["--ro-bind-try", p_res, p_res])

        for arg in cmd:
            if arg.endswith(".py") or Path(arg).exists():
                p_arg = Path(arg).resolve()
                builder.args.extend(["--ro-bind-try", str(p_arg.parent), str(p_arg.parent)])

        return builder.build(cmd)
