"""
Declarative Desktop Resource & IPC Socket Resolver for Bubblewrap sandboxes.
Translates generic resource specifiers into bwrap execution arguments.
"""

import os
from pathlib import Path

from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)


def _resolve_display_bind() -> list[str]:
    """Resolve dynamic Wayland / X11 display socket mounts for GUI strands."""
    args = []
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if wayland_display and runtime:
        wl_sock = os.path.join(runtime, wayland_display)
        if Path(wl_sock).exists():
            args.extend(
                [
                    "--ro-bind",
                    wl_sock,
                    wl_sock,
                    "--setenv",
                    "WAYLAND_DISPLAY",
                    wayland_display,
                    "--setenv",
                    "XDG_RUNTIME_DIR",
                    runtime,
                ]
            )
    if x11_display := os.environ.get("DISPLAY"):
        args.extend(["--setenv", "DISPLAY", x11_display])
        x11_sock = os.path.join("/", "tmp", ".X11-unix")
        if Path(x11_sock).exists():
            args.extend(["--ro-bind", x11_sock, x11_sock])
    return args


def _resolve_sound_bind() -> list[str]:
    """Resolve dynamic PipeWire / PulseAudio sound socket mounts for audio strands."""
    args = []
    if runtime := os.environ.get("XDG_RUNTIME_DIR"):
        for sock_name in ("pipewire-0", "pulse"):
            p = os.path.join(runtime, sock_name)
            if Path(p).exists():
                args.extend(["--ro-bind", p, p])
    return args


def _resolve_dbus_session_bind() -> list[str]:
    """Resolve dynamic D-Bus session bus socket mount."""
    args = []
    bus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if bus_addr:
        args.extend(["--setenv", "DBUS_SESSION_BUS_ADDRESS", bus_addr])
        if "unix:path=" in bus_addr:
            sock_path = bus_addr.split("unix:path=")[1].split(",")[0]
            if Path(sock_path).exists():
                args.extend(["--ro-bind", sock_path, sock_path])
    elif runtime := os.environ.get("XDG_RUNTIME_DIR"):
        default_bus = os.path.join(runtime, "bus")
        if Path(default_bus).exists():
            args.extend(
                [
                    "--ro-bind",
                    default_bus,
                    default_bus,
                    "--setenv",
                    "DBUS_SESSION_BUS_ADDRESS",
                    f"unix:path={default_bus}",
                ]
            )
    return args


def _resolve_dbus_system_bind() -> list[str]:
    """Resolve dynamic D-Bus system bus socket mount."""
    args = []
    for sys_bus in ("/run/dbus/system_bus_socket", "/var/run/dbus/system_bus_socket"):
        if Path(sys_bus).exists():
            args.extend(["--ro-bind", sys_bus, sys_bus])
            break
    return args


def _resolve_socket_bind(socket_spec: str) -> list[str]:
    """Resolve unix domain socket or socket directory mount."""
    args = []
    expanded = os.path.expandvars(os.path.expanduser(socket_spec))
    sock_path = Path(expanded)
    if sock_path.exists():
        args.extend(["--ro-bind", str(sock_path), str(sock_path)])
    elif sock_path.parent.exists():
        args.extend(["--ro-bind-try", str(sock_path.parent), str(sock_path.parent)])
    return args


def _resolve_env_spec(env_spec: str) -> list[str]:
    """Resolve environment variable passing into sandbox."""
    args = []
    if "=" in env_spec:
        k, v = env_spec.split("=", 1)
        args.extend(["--setenv", k, v])
    elif val := os.environ.get(env_spec):
        args.extend(["--setenv", env_spec, val])
    return args


def resolve_sandbox_resources(resources: list[str]) -> list[str]:
    """
    Generically resolve declarative sandbox resource specifiers into Bubblewrap execution arguments.

    Supported specifiers:
      - "display", "display:wayland", "display:x11": Wayland / X11 display sockets and environment.
      - "sound", "sound:pipewire", "sound:pulseaudio": PipeWire / PulseAudio audio sockets.
      - "dbus:session", "dbus-session": D-Bus session bus socket and DBUS_SESSION_BUS_ADDRESS.
      - "dbus:system", "dbus-system": D-Bus system bus socket (/run/dbus/system_bus_socket).
      - "socket:<path>": Arbitrary Unix domain socket file or containing directory.
      - "env:<var>" or "env:<var>=<val>": Environment variable passing into the sandbox.
    """
    args: list[str] = []
    for res_name in resources:
        clean_res = res_name.strip()
        if not clean_res:
            continue

        lowered = clean_res.lower()
        if lowered in ("display", "display:wayland", "display:x11"):
            args.extend(_resolve_display_bind())
        elif lowered in ("sound", "sound:pipewire", "sound:pulseaudio"):
            args.extend(_resolve_sound_bind())
        elif lowered in ("dbus:session", "dbus-session"):
            args.extend(_resolve_dbus_session_bind())
        elif lowered in ("dbus:system", "dbus-system"):
            args.extend(_resolve_dbus_system_bind())
        elif lowered.startswith("socket:"):
            raw_path = clean_res[7:].strip()
            args.extend(_resolve_socket_bind(raw_path))
        elif lowered.startswith("env:"):
            raw_env = clean_res[4:].strip()
            args.extend(_resolve_env_spec(raw_env))
        else:
            logger.warning("sandbox.unrecognized_resource_requested", resource=res_name)
    return args
