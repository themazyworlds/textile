"""
Native Linux Virtual Input Capability Yarn powered by /dev/uinput and ydotool.
Provides Layer 50 (Desktop Protocol).
"""

import contextlib
import os
import shutil
import socket
import subprocess
import time

try:
    import pyxclip
except ImportError:
    pyxclip = None

from textile.core.base import CapabilityTier, Yarn, strand
from textile.yarns.hyprland.hyprland import hyprland_ipc


class Ydotool(Yarn):

    KEY_MAP = {
        "enter": 28,
        "return": 28,
        "esc": 1,
        "escape": 1,
        "backspace": 14,
        "tab": 15,
        "space": 57,
        "up": 103,
        "down": 108,
        "left": 105,
        "right": 106,
        "home": 102,
        "end": 107,
        "pageup": 104,
        "pagedown": 109,
        "delete": 111,
        "ctrl": 29,
        "shift": 42,
        "alt": 56,
        "super": 125,
    }

    def is_available(self) -> bool:
        return hasattr(os, "getuid") and (shutil.which("ydotool") is not None or shutil.which("wtype") is not None)

    def _get_env(self) -> dict[str, str]:
        uid = getattr(os, "getuid", lambda: 1000)()
        env = os.environ.copy()
        env["YDOTOOL_SOCKET"] = f"/run/user/{uid}/.ydotool_socket"
        return env

    def _is_socket_alive(self, path: str) -> bool:
        if not os.path.exists(path) or not hasattr(socket, "AF_UNIX"):
            return False
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            s.close()
            return True
        except OSError:
            return False

    def _ensure_daemon(self) -> bool:
        uid = getattr(os, "getuid", lambda: 1000)()
        sock_path = f"/run/user/{uid}/.ydotool_socket"
        ydotoold_bin = shutil.which("ydotoold")
        if not ydotoold_bin:
            return False

        if not self._is_socket_alive(sock_path):
            if os.path.exists(sock_path):
                with contextlib.suppress(OSError):
                    os.remove(sock_path)
            try:
                subprocess.Popen(
                    [ydotoold_bin],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                time.sleep(0.35)
            except (OSError, subprocess.SubprocessError):
                return False
        return True

    @strand(
        description="Type text, commands, or passwords directly into active focused window or terminal.",
        tier=CapabilityTier.INTERACT,
    )
    def type_text(self, text: str, press_enter: bool = True, delay_ms: int = 12) -> str:
        """Type text, commands, or passwords directly into the active focused window.

        :param text: Text or password to type.
        :param press_enter: Press Enter after typing (default true).
        :param delay_ms: Delay in ms between keystrokes (default 12ms).
        """
        if not text:
            return "Error: No text provided."
        delay = max(1, min(int(delay_ms), 200))

        self._ensure_daemon()

        ydotool_bin = shutil.which("ydotool")
        if ydotool_bin:
            try:
                res = subprocess.run(
                    [ydotool_bin, "type", "-d", str(delay), text],
                    env=self._get_env(),
                    capture_output=True,
                    text=True,
                    timeout=8,
                    check=False,
                )
                if res.returncode == 0:
                    if press_enter:
                        time.sleep(0.06)
                        subprocess.run(
                            [ydotool_bin, "key", "28:1", "28:0"],
                            env=self._get_env(),
                            capture_output=True,
                            timeout=4,
                            check=False,
                        )
                    return "Successfully typed text into active window."
                err = res.stdout.strip() or res.stderr.strip()
                if err:
                    return f"ydotool error: {err}"
            except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError, KeyError) as e:
                return f"Error running ydotool: {e}"

        wtype_bin = shutil.which("wtype")
        if wtype_bin:
            try:
                w_cmd = [wtype_bin, "-d", str(delay), text]
                if press_enter:
                    w_cmd.extend(["-k", "Return"])
                res2 = subprocess.run(w_cmd, capture_output=True, text=True, timeout=8, check=False)
                if res2.returncode == 0:
                    return "Successfully typed text via wtype."
                return f"wtype error: {res2.stderr.strip()}"
            except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError, KeyError) as e:
                return f"Error typing text via wtype: {e}"

        return "Error: Virtual keyboard daemon (ydotool) could not connect."

    @strand(description="Press a specific keyboard key or hotkey combination.", tier=CapabilityTier.INTERACT)
    def press_key(self, key: str, modifiers: str | None = None) -> str:
        """Press a specific keyboard key or hotkey combination.

        :param key: Key name (e.g. 'enter', 'tab', 'escape', 'up', 'down').
        :param modifiers: Comma-separated modifier keys (e.g. 'ctrl', 'alt', 'shift', 'super').
        """
        key_name = str(key).strip().lower()
        modifiers_str = str(modifiers or "").strip().lower()
        if not key_name:
            return "Error: No key provided."

        self._ensure_daemon()

        ydotool_bin = shutil.which("ydotool")
        if ydotool_bin:
            try:
                key_code = self.KEY_MAP.get(key_name)
                mod_codes = [self.KEY_MAP[m.strip()] for m in modifiers_str.split(",") if m.strip() in self.KEY_MAP]
                events = []
                for m in mod_codes:
                    events.append(f"{m}:1")
                if key_code is not None:
                    events.extend([f"{key_code}:1", f"{key_code}:0"])
                else:
                    subprocess.run(
                        [ydotool_bin, "type", key_name],
                        env=self._get_env(),
                        capture_output=True,
                        timeout=4,
                        check=False,
                    )
                for m in reversed(mod_codes):
                    events.append(f"{m}:0")
                if events:
                    subprocess.run(
                        [ydotool_bin, "key", *events],
                        env=self._get_env(),
                        capture_output=True,
                        timeout=4,
                        check=False,
                    )
                return f"Successfully pressed key '{key_name}'."
            except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError, KeyError) as e:
                return f"Error pressing key: {e}"

        return "Error: ydotool is not available."

    @strand(description="Paste text or clipboard content into the active focused window.", tier=CapabilityTier.INTERACT)
    def paste_text(
        self,
        text: str | None = None,
        is_terminal: bool | None = None,
        press_enter: bool = False,
    ) -> str:
        """Paste text or clipboard content into the active focused window.

        :param text: Text to copy and paste. If omitted, pastes current clipboard.
        :param is_terminal: Terminal window flag (Ctrl+Shift+V vs Ctrl+V).
        :param press_enter: Press Enter after pasting.
        """
        if text and str(text).strip() and pyxclip is not None:
            with contextlib.suppress(OSError, AttributeError):
                if hasattr(pyxclip, "copy"):
                    pyxclip.copy(str(text))

        term_mode = is_terminal
        if term_mode is None:
            try:
                active_win = hyprland_ipc.get_active_window()
                cls_name = str(active_win.get("class", "")).lower()
                term_terms = ("foot", "kitty", "alacritty", "ghostty", "wezterm", "terminal", "xterm", "console")
                term_mode = any(t in cls_name for t in term_terms)
            except (OSError, ValueError, TypeError, AttributeError, KeyError):
                term_mode = False

        self._ensure_daemon()

        ydotool_bin = shutil.which("ydotool")
        if ydotool_bin:
            try:
                events = (
                    ["29:1", "42:1", "47:1", "47:0", "42:0", "29:0"]
                    if term_mode
                    else ["29:1", "47:1", "47:0", "29:0"]
                )
                if press_enter:
                    events.extend(["28:1", "28:0"])
                res = subprocess.run(
                    [ydotool_bin, "key", *events],
                    env=self._get_env(),
                    capture_output=True,
                    text=True,
                    timeout=4,
                    check=False,
                )
                if res.returncode == 0:
                    target_mode = "Terminal (Ctrl+Shift+V)" if term_mode else "GUI application (Ctrl+V)"
                    return f"Successfully pasted clipboard text into {target_mode}."
                return f"ydotool paste returned code {res.returncode}: {res.stderr.strip()}"
            except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError, KeyError) as e:
                return f"Error executing paste: {e}"

        return "Error: ydotool is not available."
