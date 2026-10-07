"""
Bubblewrap (bwrap) unprivileged container builder and isolation manager.
Enforces mount isolation, network namespaces, and capability tier bounds.
"""

import os
import shutil
import subprocess
import sys
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

    def set_namespaces(self, allow_network: bool) -> BubblewrapBuilder:
        self.args.extend(["--unshare-user", "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--die-with-parent"])
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
    """Bind virtualenv and sys.prefix locations into sandbox if not standard system paths."""
    for check_path in (sys.prefix, sys.base_prefix, getattr(sys, "base_exec_prefix", None)):
        if check_path and Path(check_path).exists():
            p_resolved = str(Path(check_path).resolve())
            if not any(p_resolved.startswith(prefix) for prefix in ("/usr", "/lib", "/opt", "/nix")):
                builder.args.extend(["--ro-bind-try", p_resolved, p_resolved])


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
            elif not any(p_str.startswith(prefix) for prefix in ("/usr", "/bin", "/lib", "/opt", "/nix")):
                parent_dir = str(Path(p_str).parent)
                builder.args.extend(["--ro-bind-try", parent_dir, parent_dir])


class BubblewrapSandbox:
    """
    Linux Bubblewrap (bwrap) unprivileged container isolation manager.
    Enforces namespace isolation (mount, PID, IPC, network) and workspace confinement.
    """

    @classmethod
    def is_available(cls) -> bool:
        """Check if bubblewrap (bwrap) executable is present and working."""
        if sys.platform != "linux":
            return False
        bwrap_path = shutil.which("bwrap")
        if not bwrap_path:
            return False
        try:
            res = subprocess.run(
                [bwrap_path, "--version"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            return res.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @classmethod
    def wrap_command(
        cls,
        cmd: list[str],
        tier: str,
        *,
        workspace_root: str | Path | None = None,
        allow_network: bool = False,
        resources: list[str] | None = None,
    ) -> list[str]:
        """Wrap command in a bwrap sandbox container tailored to the capability tier."""
        bwrap_path = shutil.which("bwrap")
        tier_upper = tier.upper()
        if "PRIVILEGED" in tier_upper:
            return cmd

        if not bwrap_path:
            raise SandboxUnavailableError("bwrap binary not found in system PATH.")

        is_writable = "MUTATE" in tier_upper
        ws = Path(workspace_root or Path.cwd()).resolve()
        container_tmp = os.path.join("/", "tmp")
        container_home = os.path.join("/", "home")
        uv_cache = os.path.join(container_tmp, "uv_cache")

        builder = (
            BubblewrapBuilder(bwrap_path)
            .bind_system_base()
            .bind_tmpfs([container_tmp, container_home])
            .bind_resources(resources)
            .set_namespaces(allow_network)
            .bind_workspace(ws, is_writable)
            .set_env("PATH", os.environ.get("PATH", "/usr/bin:/bin"))
            .set_env("UV_CACHE_DIR", uv_cache)
            .set_env("PYTHONPATH", os.environ.get("PYTHONPATH"))
        )

        _bind_user_config_and_share(builder)
        _bind_python_prefixes(builder)
        _bind_executable_dependencies(builder, cmd)

        return builder.build(cmd)
