"""
Declarative Desktop Resource & IPC Socket Resolver for Bubblewrap sandboxes.
Translates generic resource specifiers into strongly typed BubblewrapBuilder operations.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from textile.core.security.sandbox.builder import BubblewrapBuilder
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)


def _apply_display_resource(builder: BubblewrapBuilder) -> None:
    """Resolve and mount Wayland / X11 display socket and environment for GUI strands."""
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if wayland_display and runtime:
        wl_sock = os.path.join(runtime, wayland_display)
        if Path(wl_sock).exists():
            builder.ro_bind(wl_sock).setenv("WAYLAND_DISPLAY", wayland_display).setenv("XDG_RUNTIME_DIR", runtime)

    if x11_display := os.environ.get("DISPLAY"):
        builder.setenv("DISPLAY", x11_display)
        x11_sock = os.path.join("/", "tmp", ".X11-unix")
        if Path(x11_sock).exists():
            builder.ro_bind(x11_sock)


def _apply_sound_resource(builder: BubblewrapBuilder) -> None:
    """Resolve and mount PipeWire / PulseAudio sound socket for audio strands."""
    if runtime := os.environ.get("XDG_RUNTIME_DIR"):
        for sock_name in ("pipewire-0", "pulse"):
            p = os.path.join(runtime, sock_name)
            if Path(p).exists():
                builder.ro_bind(p)


def _apply_dbus_session_resource(builder: BubblewrapBuilder) -> None:
    """Resolve and mount D-Bus session bus socket and environment."""
    if (runtime := os.environ.get("XDG_RUNTIME_DIR")) and Path(runtime).exists():
        builder.bind(runtime).setenv("XDG_RUNTIME_DIR", runtime)

    bus_addr = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if bus_addr:
        builder.setenv("DBUS_SESSION_BUS_ADDRESS", bus_addr)
        if "unix:path=" in bus_addr:
            sock_path = bus_addr.split("unix:path=")[1].split(",")[0]
            if Path(sock_path).exists():
                builder.ro_bind(sock_path)
    elif runtime:
        default_bus = os.path.join(runtime, "bus")
        if Path(default_bus).exists():
            builder.setenv("DBUS_SESSION_BUS_ADDRESS", f"unix:path={default_bus}")


def _apply_dbus_system_resource(builder: BubblewrapBuilder) -> None:
    """Resolve and mount D-Bus system bus socket."""
    for sys_bus in ("/run/dbus/system_bus_socket", "/var/run/dbus/system_bus_socket"):
        if Path(sys_bus).exists():
            builder.ro_bind(sys_bus)
            break


def _apply_socket_resource(builder: BubblewrapBuilder, socket_spec: str) -> None:
    """Resolve and mount Unix domain socket or containing directory."""
    expanded = os.path.expandvars(os.path.expanduser(socket_spec))
    sock_path = Path(expanded)
    if sock_path.exists():
        builder.ro_bind(sock_path)
    elif sock_path.parent.exists():
        builder.ro_bind(sock_path.parent, try_ok=True)


def _apply_env_resource(builder: BubblewrapBuilder, env_spec: str) -> None:
    """Resolve and inject environment variables into container."""
    if "=" in env_spec:
        k, v = env_spec.split("=", 1)
        builder.setenv(k, v)
    elif val := os.environ.get(env_spec):
        builder.setenv(env_spec, val)


def apply_sandbox_resources(builder: BubblewrapBuilder, resources: Sequence[str]) -> None:
    """
    Apply declarative resource specifiers directly to a BubblewrapBuilder instance.

    Supported specifiers:
      - "display", "display:wayland", "display:x11": Wayland / X11 display sockets and environment.
      - "sound", "sound:pipewire", "sound:pulseaudio": PipeWire / PulseAudio audio sockets.
      - "dbus:session", "dbus-session": D-Bus session bus socket and DBUS_SESSION_BUS_ADDRESS.
      - "dbus:system", "dbus-system": D-Bus system bus socket (/run/dbus/system_bus_socket).
      - "socket:<path>": Arbitrary Unix domain socket file or containing directory.
      - "env:<var>" or "env:<var>=<val>": Environment variable passing into the sandbox.
    """
    for res_name in resources:
        clean_res = res_name.strip()
        if not clean_res:
            continue

        lowered = clean_res.lower()
        if lowered in ("display", "display:wayland", "display:x11"):
            _apply_display_resource(builder)
        elif lowered in ("sound", "sound:pipewire", "sound:pulseaudio"):
            _apply_sound_resource(builder)
        elif lowered in ("dbus:session", "dbus-session"):
            _apply_dbus_session_resource(builder)
        elif lowered in ("dbus:system", "dbus-system"):
            _apply_dbus_system_resource(builder)
        elif lowered.startswith("socket:"):
            _apply_socket_resource(builder, clean_res[7:].strip())
        elif lowered.startswith("env:"):
            _apply_env_resource(builder, clean_res[4:].strip())
        else:
            logger.warning("sandbox.unrecognized_resource_requested", resource=res_name)
