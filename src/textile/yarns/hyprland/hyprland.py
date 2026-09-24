"""
Hyprland Compositor Direct Socket IPC Capability Yarn.
Bypasses subshell forks with direct UNIX domain socket IPC communication.
Layer 100 (Compositor / DE).
"""

import contextlib
import glob
import json
import os
import select
import shutil
import socket
import subprocess
import time
from typing import Any, Literal

from textile.core.base import Yarn, strand


class HyprlandIPC:
    """Direct IPC client connecting to Hyprland's native UNIX domain socket."""

    def __init__(self):
        self._signature: str = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        self._runtime_dir: str = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

    def _get_socket_path(self) -> str:
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", self._signature)
        if sig:
            candidates = [
                f"{self._runtime_dir}/hypr/{sig}/.socket.sock",
                f"/tmp/hypr/{sig}/.socket.sock",  # noqa: S108
            ]
            for c in candidates:
                if os.path.exists(c):
                    return c
        return f"{self._runtime_dir}/hypr/{sig}/.socket.sock"

    def _get_event_socket_path(self) -> str:
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", self._signature)
        if sig:
            candidates = [
                f"{self._runtime_dir}/hypr/{sig}/.socket2.sock",
                f"/tmp/hypr/{sig}/.socket2.sock",  # noqa: S108
            ]
            for c in candidates:
                if os.path.exists(c):
                    return c
        return f"{self._runtime_dir}/hypr/{sig}/.socket2.sock"

    def send_raw(self, command: str) -> str:
        sock_path = self._get_socket_path()
        if not os.path.exists(sock_path):
            return ""

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(1.5)
            sock.connect(sock_path)
            sock.sendall(command.encode("utf-8"))
            data = bytearray()
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
            return data.decode("utf-8", errors="replace")
        except OSError:
            return ""
        finally:
            sock.close()

    def send_json(self, command: str) -> Any:
        raw = self.send_raw(command)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def dispatch(self, lua_disp_call: str) -> str:
        cmd = f"dispatch {lua_disp_call}".strip()
        return self.send_raw(cmd).strip()

    def focus_workspace(self, workspace: str) -> str:
        ws_literal = json.dumps(str(workspace).strip())
        return self.dispatch(f"hl.dsp.focus({{ workspace = {ws_literal} }})")

    @staticmethod
    def _detect_terminal() -> str:
        for term in ("foot", "kitty", "alacritty", "ghostty", "wezterm", "st", "urxvt", "xterm"):
            if shutil.which(term):
                return term
        return "xterm"

    @staticmethod
    def _detect_shell() -> str:
        user_shell = os.environ.get("SHELL", "")
        if user_shell and shutil.which(user_shell):
            return user_shell
        for sh in ("zsh", "bash", "fish", "sh"):
            if shutil.which(sh):
                return sh
        return "/bin/sh"

    def exit_session(self) -> str:
        return self.dispatch("exit")

    def _get_self_ancestor_pids(self) -> list[int]:
        ancestors = []
        curr = os.getpid()
        visited = set()
        while curr > 1 and curr not in visited:
            visited.add(curr)
            ancestors.append(curr)
            try:
                with open(f"/proc/{curr}/stat") as f:
                    stat = f.read().split()
                    curr = int(stat[3])
            except (OSError, ValueError, IndexError):
                break
        return ancestors

    def _get_self_descendant_command_lines(self, root_pid: int) -> list[str]:
        parent_map: dict[int, list[int]] = {}
        proc_info: dict[int, str] = {}
        proc_cmdlines: dict[int, str] = {}
        try:
            for p_dir in glob.glob("/proc/[0-9]*"):
                with contextlib.suppress(OSError, ValueError, TypeError, KeyError, IndexError):
                    pid = int(os.path.basename(p_dir))
                    with open(f"{p_dir}/stat") as f:
                        stat = f.read().split()
                        comm = stat[1].strip("()")
                        ppid = int(stat[3])
                        parent_map.setdefault(ppid, []).append(pid)
                        proc_info[pid] = comm.lower()
                    with open(f"{p_dir}/cmdline", "rb") as cmdf:
                        cmd_str = cmdf.read().decode("utf-8", errors="ignore").replace("\x00", " ").lower()
                        proc_cmdlines[pid] = cmd_str
        except (OSError, ValueError):
            return []

        descendants = []
        queue = [root_pid]
        visited = {root_pid}
        while queue:
            curr = queue.pop(0)
            for ch in parent_map.get(curr, []):
                if ch not in visited:
                    visited.add(ch)
                    comm = proc_info.get(ch, "")
                    cmdline = proc_cmdlines.get(ch, "")
                    if comm:
                        descendants.append(comm)
                    if cmdline:
                        descendants.append(cmdline)
                    queue.append(ch)
        return descendants

    def get_self_window(self) -> dict[str, Any] | None:
        ancestors = self._get_self_ancestor_pids()
        clients = self.get_clients()
        for c in clients:
            if c.get("pid") in ancestors:
                return c
        return None

    def _resolve_special_target(self, target_lower: str) -> dict[str, Any] | None:
        active_aliases = (
            "active", "active window", "active_window",
            "focused", "focused window", "focused_window",
            "current", "current window", "current_window",
        )
        if target_lower in active_aliases:
            return self.get_active_window() or None

        self_keywords = (
            "textile", "weave", "twill", "agy", "agy_cli", "self",
            "you", "yourself", "this", "this window", "my window", "your window", "here",
        )
        if target_lower in self_keywords:
            return self.get_self_window() or None
        return None

    def _resolve_prefixed_target(self, target_clean: str, clients: list[dict[str, Any]]) -> dict[str, Any] | None:
        if target_clean.startswith("0x"):
            for c in clients:
                if c.get("address", "").lower() == target_clean.lower():
                    return c
            return {"address": target_clean}

        if any(target_clean.startswith(p) for p in ("class:", "title:", "pid:", "address:")):
            prefix, _, val = target_clean.partition(":")
            val_lower = val.lower()
            if prefix == "class":
                for c in clients:
                    if c.get("class", "").lower() == val_lower:
                        return c
            elif prefix == "title":
                for c in clients:
                    if val_lower in c.get("title", "").lower():
                        return c
            elif prefix == "pid" and val.isdigit():
                pid_int = int(val)
                for c in clients:
                    if c.get("pid") == pid_int:
                        return c
            elif prefix == "address":
                for c in clients:
                    if c.get("address", "").lower() == val_lower:
                        return c
                return {"address": val}
        return None

    def _score_client(
        self,
        c: dict[str, Any],
        target_lower: str,
        keywords: list[str],
        is_querying_self: bool,
        self_ancestors: list[int],
    ) -> int:
        score = 0
        title = c.get("title", "").lower()
        cls_name = c.get("class", "").lower()
        init_cls = c.get("initialClass", "").lower()
        init_title = c.get("initialTitle", "").lower()
        pid = c.get("pid", 0)
        is_self_window = pid in self_ancestors

        child_procs = self._get_self_descendant_command_lines(pid)
        proc_matched = False
        for proc_str in child_procs:
            proc_str_clean = proc_str.strip().lower()
            for kw in keywords:
                if kw == proc_str_clean:
                    score += 500
                    proc_matched = True
                elif kw in proc_str_clean.split():
                    score += 300
                    proc_matched = True
                elif kw in proc_str_clean:
                    score += 150
                    proc_matched = True

        if target_lower in title:
            score += 200
        for kw in keywords:
            if kw in title.split():
                score += 120
            elif kw in title:
                score += 60

        for kw in keywords:
            if kw == cls_name:
                score += 100 if proc_matched else 30
            elif kw in cls_name:
                score += 15
            if kw in init_cls or kw in init_title:
                score += 10

        if is_self_window and not is_querying_self:
            score -= 1000

        focus_hist = c.get("focusHistoryID", 99)
        if isinstance(focus_hist, int):
            score += max(0, 10 - focus_hist)
        return score

    def resolve_window(self, target: str) -> dict[str, Any] | None:
        target_clean = str(target).strip()
        if not target_clean:
            return None
        target_lower = target_clean.lower()

        special = self._resolve_special_target(target_lower)
        if special:
            return special

        clients = self.get_clients()
        if not clients:
            return None

        prefixed = self._resolve_prefixed_target(target_clean, clients)
        if prefixed:
            return prefixed

        keywords = [w for w in target_lower.split() if w]
        self_keywords = (
            "textile", "weave", "twill", "agy", "agy_cli", "self",
            "you", "yourself", "this", "this window", "my window", "your window", "here",
        )
        is_querying_self = any(k in target_lower for k in self_keywords)
        self_ancestors = self._get_self_ancestor_pids()

        scored_clients = []
        for c in clients:
            addr = c.get("address", "").lower()
            if target_lower in addr or target_lower == addr:
                return c
            score = self._score_client(c, target_lower, keywords, is_querying_self, self_ancestors)
            if score > 0:
                scored_clients.append((score, c))

        scored_clients.sort(key=lambda x: x[0], reverse=True)
        if scored_clients and scored_clients[0][0] > 0:
            return scored_clients[0][1]
        return None

    def focus_window(self, target: str) -> str:
        target_clean = str(target).strip()
        if not target_clean:
            return "Error: No target window specified."
        win = self.resolve_window(target_clean)
        if win and "address" in win:
            addr_literal = json.dumps(f"address:{win['address']}")
            return self.dispatch(f"hl.dsp.focus({{ window = {addr_literal} }})")
        return f"Error: No open window found matching '{target_clean}'."

    def close_window(self, target: str | None = None) -> str:
        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if win and "address" in win:
                addr_literal = json.dumps(f"address:{win['address']}")
                return self.dispatch(f"hl.dsp.window.close({{ window = {addr_literal} }})")
            return f"Error: No open window found matching '{target_clean}'."
        return self.dispatch("hl.dsp.window.close({})")

    def move_to_workspace(self, workspace: str, target: str | None = None, silent: bool = False) -> str:
        ws_literal = json.dumps(str(workspace).strip())
        current_ws = None
        if silent:
            act = self.get_active_workspace()
            current_ws = act.get("name") or act.get("id")

        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if win and "address" in win:
                addr_literal = json.dumps(f"address:{win['address']}")
                res = self.dispatch(f"hl.dsp.window.move({{ window = {addr_literal}, workspace = {ws_literal} }})")
                if silent and current_ws:
                    self.focus_workspace(str(current_ws))
                return res
            return f"Error: No open window found matching '{target_clean}'."

        res = self.dispatch(f"hl.dsp.window.move({{ workspace = {ws_literal} }})")
        if silent and current_ws:
            self.focus_workspace(str(current_ws))
        return res

    def window_action(self, action: str, target: str | None = None) -> str:
        act = action.lower().strip()
        win_param = ""
        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if not win or "address" not in win:
                return f"Error: No open window found matching '{target_clean}'."
            addr_literal = json.dumps(f"address:{win['address']}")
            win_param = f"window = {addr_literal}"

        if act in ("close", "kill"):
            return self.close_window(target=target)
        elif act in ("float", "togglefloating"):
            return self.dispatch(f"hl.dsp.window.float({{{win_param}}})")
        elif act in ("fullscreen", "toggle_fullscreen"):
            if win_param:
                self.dispatch(f"hl.dsp.focus({{{win_param}}})")
            return self.dispatch(f"hl.dsp.window.fullscreen({{{win_param}}})")
        elif act == "pin":
            return self.dispatch(f"hl.dsp.window.pin({{{win_param}}})")
        elif act == "center":
            return self.dispatch(f"hl.dsp.window.center({{{win_param}}})")
        else:
            return self.dispatch(f"hl.dsp.window.{act}({{{win_param}}})")

    def focus_direction(self, direction: str) -> str:
        dir_literal = json.dumps(direction.lower().strip())
        return self.dispatch(f"hl.dsp.focus({{ direction = {dir_literal} }})")

    def move_window(
        self,
        delta_x: int = 0,
        delta_y: int = 0,
        direction: str | None = None,
        relative: bool = True,
        target: str | None = None,
    ) -> str:
        rel_str = "true" if relative else "false"
        win_param = ""
        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if not win or "address" not in win:
                return f"Error: No open window found matching '{target_clean}'."
            addr_literal = json.dumps(f"address:{win['address']}")
            win_param = f", window = {addr_literal}"

        if direction:
            dir_literal = json.dumps(direction.lower().strip())
            return self.dispatch(f"hl.dsp.window.move({{ direction = {dir_literal}{win_param} }})")

        return self.dispatch(
            f"hl.dsp.window.move({{ x = {int(delta_x)}, y = {int(delta_y)}, relative = {rel_str}{win_param} }})"
        )

    def resize_window(
        self,
        delta_x: int = 0,
        delta_y: int = 0,
        relative: bool = True,
        target: str | None = None,
    ) -> str:
        rel_str = "true" if relative else "false"
        win_param = ""
        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if not win or "address" not in win:
                return f"Error: No open window found matching '{target_clean}'."
            addr_literal = json.dumps(f"address:{win['address']}")
            win_param = f", window = {addr_literal}"
        return self.dispatch(
            f"hl.dsp.window.resize({{ x = {int(delta_x)}, y = {int(delta_y)}, relative = {rel_str}{win_param} }})"
        )

    def exec_app(self, app: str, is_tui: bool = False, title: str | None = None) -> str:
        app_clean = app.strip()
        if is_tui:
            term = self._detect_terminal()
            shell = self._detect_shell()
            app_base = app_clean.split()[0]
            title_str = title or app_base
            shell_args = f'{shell} -i -c "{app_clean}"'

            if term == "foot":
                cmd = f"{term} -a {app_base} -T {title_str} {shell_args}"
            elif term in ("kitty", "alacritty", "ghostty"):
                cmd = f"{term} -T {title_str} -- {shell_args}"
            else:
                cmd = f"{term} -e {shell_args}"
        else:
            cmd = app_clean

        cmd_literal = json.dumps(cmd)
        return self.dispatch(f"hl.dsp.exec_cmd({cmd_literal})")

    def get_active_workspace(self) -> dict[str, Any]:
        res = self.send_json("j/activeworkspace")
        return res if isinstance(res, dict) else {}

    def get_workspaces(self) -> list[dict[str, Any]]:
        res = self.send_json("j/workspaces")
        return res if isinstance(res, list) else []

    def get_active_window(self) -> dict[str, Any]:
        res = self.send_json("j/activewindow")
        return res if isinstance(res, dict) else {}

    def get_clients(self) -> list[dict[str, Any]]:
        res = self.send_json("j/clients")
        return res if isinstance(res, list) else []

    def set_monitor(self, output: str, mode: str, position: str = "0x0", scale: float = 1.25) -> str:
        out_clean = output.strip()
        mode_clean = mode.strip()
        pos_clean = position.strip()
        cmd = f"keyword monitor {out_clean},{mode_clean},{pos_clean},{scale}"
        res = self.send_raw(cmd).strip()
        return f"Monitor '{out_clean}' configured to {mode_clean} at {pos_clean} (scale {scale}): {res}"

    def get_monitors(self) -> list[dict[str, Any]]:
        res = self.send_json("j/monitors")
        return res if isinstance(res, list) else []

    def read_events(self, timeout: float = 0.1, max_events: int = 20) -> list[dict[str, str]]:
        sock_path = self._get_event_socket_path()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.setblocking(False)
        events = []
        try:
            sock.connect(sock_path)
        except BlockingIOError:
            pass
        except (OSError, ValueError) as e:
            sock.close()
            return [{"event": "error", "data": str(e)}]

        try:
            safe_timeout = max(0.01, min(float(timeout if timeout is not None else 0.1), 0.5))
            r, _, _ = select.select([sock], [], [], safe_timeout)
            if not r:
                return []
            buffer = ""
            while len(events) < max_events:
                try:
                    chunk = sock.recv(4096).decode("utf-8", errors="replace")
                    if not chunk:
                        break
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or ">>" not in line:
                            continue
                        event_name, _, event_data = line.partition(">>")
                        events.append({"event": event_name.strip(), "data": event_data.strip()})
                        if len(events) >= max_events:
                            break
                    r, _, _ = select.select([sock], [], [], 0.02)
                    if not r:
                        break
                except (OSError, BlockingIOError):
                    break
        except (OSError, ValueError) as e:
            if not events:
                events.append({"event": "error", "data": str(e)})
        finally:
            sock.close()
        return events

    def set_night_light(
        self,
        temperature: int | str | None = None,
        gamma: float | None = None,
        identity: bool = False,
    ) -> dict[str, Any]:
        hyprsunset_bin = shutil.which("hyprsunset")
        wlsunset_bin = shutil.which("wlsunset")
        if not hyprsunset_bin and not wlsunset_bin:
            return {"success": False, "error": "Neither hyprsunset nor wlsunset is installed."}

        temp_val: int | None = None
        is_ident = identity

        if isinstance(temperature, str):
            t_clean = temperature.strip().lower()
            if t_clean in ("off", "identity", "reset", "day", "daytime", "disable"):
                is_ident = True
            elif t_clean in ("night", "warm", "sunset", "evening"):
                temp_val = 4000
            elif t_clean in ("deep_night", "reading", "candle", "very_warm"):
                temp_val = 3000
            elif t_clean in ("mild", "office", "neutral"):
                temp_val = 5000
            elif t_clean.rstrip("k").isdigit():
                temp_val = int(t_clean.rstrip("k"))
        elif isinstance(temperature, (int, float)):
            temp_val = int(temperature)

        if not is_ident and temp_val is None:
            temp_val = 4000

        pkill_bin = shutil.which("pkill") or "/usr/bin/pkill"
        subprocess.run(
            [pkill_bin, "-x", "hyprsunset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
        subprocess.run(
            [pkill_bin, "-x", "wlsunset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False
        )
        time.sleep(0.1)

        if hyprsunset_bin:
            cmd = [hyprsunset_bin]
            if is_ident:
                cmd.append("-i")
            elif temp_val is not None:
                cmd.extend(["-t", str(temp_val)])
            if gamma is not None:
                cmd.extend(["-g", str(float(gamma))])
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                time.sleep(0.2)
                running = proc.poll() is None
                return {
                    "success": running,
                    "manager": "hyprsunset",
                    "pid": proc.pid if running else None,
                    "temperature_kelvin": "identity (6500K / off)" if is_ident else temp_val,
                    "gamma": gamma or 1.0,
                    "identity": is_ident,
                }
            except (OSError, subprocess.SubprocessError) as e:
                return {"success": False, "error": f"Failed to spawn hyprsunset: {e}"}
        elif wlsunset_bin:
            cmd = [wlsunset_bin]
            if is_ident:
                cmd.extend(["-t", "6500", "-T", "6500"])
            elif temp_val is not None:
                cmd.extend(["-t", str(temp_val), "-T", str(temp_val)])
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                time.sleep(0.2)
                running = proc.poll() is None
                return {
                    "success": running,
                    "manager": "wlsunset",
                    "pid": proc.pid if running else None,
                    "temperature_kelvin": "identity (6500K / off)" if is_ident else temp_val,
                    "gamma": gamma or 1.0,
                    "identity": is_ident,
                }
            except (OSError, subprocess.SubprocessError) as e:
                return {"success": False, "error": f"Failed to spawn wlsunset: {e}"}

        return {"success": False, "error": "Neither hyprsunset nor wlsunset could be launched."}

    def get_night_light_status(self) -> dict[str, Any]:
        pgrep_bin = shutil.which("pgrep") or "/usr/bin/pgrep"
        res_hypr = subprocess.run([pgrep_bin, "-la", "hyprsunset"], stdout=subprocess.PIPE, text=True, check=False)
        res_wl = subprocess.run([pgrep_bin, "-la", "wlsunset"], stdout=subprocess.PIPE, text=True, check=False)
        is_running = bool(res_hypr.stdout.strip() or res_wl.stdout.strip())
        active_mgr = "hyprsunset" if res_hypr.stdout.strip() else ("wlsunset" if res_wl.stdout.strip() else None)
        active_pid = None
        if active_mgr:
            out_str = res_hypr.stdout.strip() if active_mgr == "hyprsunset" else res_wl.stdout.strip()
            first_line = out_str.splitlines()[0]
            active_pid = int(first_line.split()[0]) if first_line.split()[0].isdigit() else None
        return {
            "is_active": is_running,
            "active_manager": active_mgr,
            "pid": active_pid,
            "hyprsunset_installed": shutil.which("hyprsunset") is not None,
            "wlsunset_installed": shutil.which("wlsunset") is not None,
        }


hyprland_ipc = HyprlandIPC()


class Hyprland(Yarn):
    def is_available(self) -> bool:
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        if sig:
            return True
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        hypr_dir = os.path.join(runtime, "hypr")
        return os.path.exists(hypr_dir) and bool(os.listdir(hypr_dir)) if os.path.exists(hypr_dir) else False

    def _parse_workspace_target(self, target: str) -> tuple[str, str | None]:
        tokens = target.split()
        min_tokens = 2
        if len(tokens) >= min_tokens and tokens[-1].lstrip("-+").isdigit():
            ws = tokens[-1]
            win_query = " ".join(tokens[:-1])
            return ws, win_query
        return target or "1", None

    @strand(
        description="Focus a Hyprland window by title, class, address, or search query.",
        tier="interact",
    )
    def hyprland_focus_window(self, target: str) -> str:
        """Focus a Hyprland window by title, class, address, or search query.

        :param target: Window title, class, address (e.g. 0x12345), or query.
        """
        return hyprland_ipc.focus_window(target)

    @strand(
        description="Switch active Hyprland workspace.",
        tier="interact",
    )
    def hyprland_focus_workspace(self, workspace: str = "1") -> str:
        """Switch active Hyprland workspace.

        :param workspace: Workspace ID, name, or relative offset (e.g. '1', 'work', '+1', '-1').
        """
        return hyprland_ipc.focus_workspace(workspace)

    @strand(
        description="Move target or active window to specified workspace.",
        tier="interact",
    )
    def hyprland_move_window_to_workspace(
        self,
        workspace: str,
        target: str | None = None,
        silent: bool = False,
    ) -> str:
        """Move target or active window to specified workspace.

        :param workspace: Target workspace ID or name.
        :param target: Window title, class, address, or query. Omit for active window.
        :param silent: If true, do not switch focus to destination workspace.
        """
        ws, win_q = self._parse_workspace_target(f"{target} {workspace}".strip() if target else str(workspace))
        return hyprland_ipc.move_to_workspace(ws, win_q, silent=silent)

    @strand(
        description="Close a window by query, address, or active window.",
        tier="interact",
    )
    def hyprland_close_window(self, target: str | None = None) -> str:
        """Close a window by query, address, or active window.

        :param target: Window query or address. Omit to close active window.
        """
        return hyprland_ipc.close_window(target=target)

    @strand(
        description="Toggle floating state for active or specified window.",
        tier="interact",
    )
    def hyprland_toggle_float(self, target: str | None = None) -> str:
        """Toggle floating state for active or specified window.

        :param target: Target window query or address.
        """
        return hyprland_ipc.window_action("float", target=target)

    @strand(
        description="Toggle fullscreen mode for active or specified window.",
        tier="interact",
    )
    def hyprland_toggle_fullscreen(self, target: str | None = None) -> str:
        """Toggle fullscreen mode for active or specified window.

        :param target: Target window query or address.
        """
        return hyprland_ipc.window_action("fullscreen", target=target)

    @strand(
        description="Pin window to show across all workspaces.",
        tier="interact",
    )
    def hyprland_pin_window(self, target: str | None = None) -> str:
        """Pin window to show across all workspaces.

        :param target: Target window query or address.
        """
        return hyprland_ipc.window_action("pin", target=target)

    @strand(
        description="Center floating window on screen.",
        tier="interact",
    )
    def hyprland_center_window(self, target: str | None = None) -> str:
        """Center floating window on screen.

        :param target: Target window query or address.
        """
        return hyprland_ipc.window_action("center", target=target)

    @strand(
        description="Move active or specified window by pixel offset or in direction (left, right, up, down).",
        tier="interact",
    )
    def hyprland_move_window(
        self,
        delta_x: int = 0,
        delta_y: int = 0,
        direction: Literal["left", "right", "up", "down"] | None = None,
        target: str | None = None,
    ) -> str:
        """Move active or specified window by pixel offset (delta_x, delta_y) or in direction (left, right, up, down).

        :param delta_x: Horizontal pixel movement delta (+100, -50).
        :param delta_y: Vertical pixel movement delta (+100, -50).
        :param direction: Directional move in layout tiling (left, right, up, down).
        :param target: Target window title, class, address, or query. Omit for active window.
        """
        return hyprland_ipc.move_window(
            delta_x=int(delta_x),
            delta_y=int(delta_y),
            direction=direction,
            target=target,
        )

    @strand(
        description="Resize active or specified window by delta X and delta Y.",
        tier="interact",
    )
    def hyprland_resize_window(
        self,
        delta_x: int,
        delta_y: int,
        target: str | None = None,
    ) -> str:
        """Resize active or specified window by delta X and delta Y.

        :param delta_x: Horizontal resize pixel delta (+20, -20).
        :param delta_y: Vertical resize pixel delta (+20, -20).
        :param target: Target window query or address.
        """
        return hyprland_ipc.resize_window(
            delta_x=int(delta_x),
            delta_y=int(delta_y),
            relative=True,
            target=target,
        )

    @strand(description="Move focus in specified direction (left, right, up, down).", tier="interact")
    def hyprland_focus_direction(
        self,
        direction: Literal["left", "right", "up", "down"] = "left",
    ) -> str:
        """Move focus in specified direction (left, right, up, down).

        :param direction: Direction to move focus.
        """
        return hyprland_ipc.focus_direction(direction)

    @strand(
        description="Set color temperature for night light / Hyprsunset.",
        tier="interact",
    )
    def hyprland_set_night_light(self, temperature: int = 4000) -> dict[str, Any]:
        """Set color temperature for night light / Hyprsunset.

        :param temperature: Color temperature in Kelvin (e.g. 3500, 4000, 6500).
        """
        return hyprland_ipc.set_night_light(temperature=int(temperature))

    @strand(
        description="Get current night light color temperature and process status.",
        tier="observe",
    )
    def hyprland_get_night_light(self) -> dict[str, Any]:
        """Get current night light color temperature and process status."""
        return hyprland_ipc.get_night_light_status()

    @strand(
        description="Configure Hyprland monitor resolution, position, and scale.",
        tier="mutate",
    )
    def hyprland_set_monitor(
        self,
        output: str,
        mode: str = "1920x1080@60",
        position: str = "0x0",
        scale: float = 1.0,
    ) -> str:
        """Configure Hyprland monitor resolution, position, and scale.

        :param output: Monitor output identifier (e.g. 'eDP-1', 'HDMI-A-1').
        :param mode: Resolution and refresh rate (e.g. '1920x1080@60').
        :param position: Position offset (e.g. '0x0', '1920x0').
        :param scale: Display scaling factor (e.g. 1.0, 1.25, 1.5).
        """
        return hyprland_ipc.set_monitor(
            output=output,
            mode=mode,
            position=position,
            scale=float(scale),
        )

    @strand(
        description="Get details of currently active workspace.",
        tier="observe",
    )
    def hyprland_get_active_workspace(self) -> dict[str, Any]:
        """Get details of currently active workspace."""
        return hyprland_ipc.get_active_workspace()

    @strand(
        description="Get details of currently focused window.",
        tier="observe",
    )
    def hyprland_get_active_window(self) -> dict[str, Any]:
        """Get details of currently focused window."""
        return hyprland_ipc.get_active_window()

    @strand(
        description="Get window details for the calling Textile / CLI process.",
        tier="observe",
    )
    def hyprland_get_self_window(self) -> dict[str, Any] | None:
        """Get window details for the calling Textile / CLI process."""
        return hyprland_ipc.get_self_window()

    @strand(
        description="List all active Hyprland workspaces.",
        tier="observe",
    )
    def hyprland_get_workspaces(self) -> list[dict[str, Any]]:
        """List all active Hyprland workspaces."""
        return hyprland_ipc.get_workspaces()

    @strand(
        description="Get window details by title, class, address, or query.",
        tier="observe",
    )
    def hyprland_get_window(self, target: str) -> dict[str, Any]:
        """Get window details by title, class, address, or query.

        :param target: Window title, class, or address.
        """
        return hyprland_ipc.resolve_window(target) or {"error": f"Window '{target}' not found"}

    @strand(
        description="List all open windows / clients in Hyprland.",
        tier="observe",
    )
    def hyprland_get_windows(self) -> list[dict[str, Any]]:
        """List all open windows / clients in Hyprland."""
        return hyprland_ipc.get_clients()

    @strand(
        description="List connected monitors and layout geometry.",
        tier="observe",
    )
    def hyprland_get_monitors(self) -> list[dict[str, Any]]:
        """List connected monitors and layout geometry."""
        return hyprland_ipc.get_monitors()

    @strand(description="Exit Hyprland compositor session (logout).", tier="privileged")
    def hyprland_exit_session(self) -> str:
        """Exit Hyprland compositor session (logout)."""
        return hyprland_ipc.exit_session()

    @strand(
        description="Launch application or shell command via Hyprland exec dispatcher.",
        capability="desktop.app_launcher",
        tier="privileged",
    )
    def hyprland_launch_app(self, command: str) -> str:
        """Launch application or shell command via Hyprland exec dispatcher.

        :param command: Command line or application name to launch.
        """
        return hyprland_ipc.exec_app(app=command)
