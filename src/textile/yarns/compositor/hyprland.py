"""
Hyprland Compositor Direct Socket IPC Capability Yarn.
Bypasses subshell forks with direct UNIX domain socket IPC communication.
Layer 100 (Compositor / DE).
"""

import json
import os
import shutil
import socket
import subprocess
import time
from typing import Any, Dict, List, Literal, Optional, Set

from textile.core.base import BaseYarn, strand, LAYER_COMPOSITOR_DE


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
                f"/tmp/hypr/{sig}/.socket.sock",
            ]
            for path in candidates:
                if os.path.exists(path):
                    return path
        import glob
        found = glob.glob(f"{self._runtime_dir}/hypr/*/.socket.sock") + glob.glob("/tmp/hypr/*/.socket.sock")
        if found:
            return found[0]
        raise FileNotFoundError("Hyprland command socket (.socket.sock) not found.")

    def _get_event_socket_path(self) -> str:
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", self._signature)
        if sig:
            candidates = [
                f"{self._runtime_dir}/hypr/{sig}/.socket2.sock",
                f"/tmp/hypr/{sig}/.socket2.sock",
            ]
            for path in candidates:
                if os.path.exists(path):
                    return path
        import glob
        found = glob.glob(f"{self._runtime_dir}/hypr/*/.socket2.sock") + glob.glob("/tmp/hypr/*/.socket2.sock")
        if found:
            return found[0]
        raise FileNotFoundError("Hyprland event socket (.socket2.sock) not found.")

    def send_raw(self, request: str) -> str:
        sock_path = self._get_socket_path()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(sock_path)
            sock.sendall(request.encode("utf-8"))
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", errors="replace")
        finally:
            sock.close()

    def send_json(self, command: str) -> Any:
        cmd = command if command.startswith("j/") else f"j/{command}"
        raw = self.send_raw(cmd)
        try:
            return json.loads(raw)
        except Exception:
            return {"raw_response": raw}

    def dispatch(self, action: str) -> str:
        return self.send_raw(f"dispatch {action}").strip()

    def focus_workspace(self, workspace: str) -> str:
        ws_str = str(workspace).strip()
        return self.dispatch(f'hl.dsp.focus({{ workspace = "{ws_str}" }})')

    @staticmethod
    def _detect_terminal() -> str:
        env_term = os.environ.get("TERMINAL")
        if env_term and shutil.which(env_term):
            return env_term
        for candidate in ["foot", "kitty", "alacritty", "ghostty", "wezterm", "gnome-terminal", "konsole", "xterm"]:
            if shutil.which(candidate):
                return candidate
        return "foot"

    @staticmethod
    def _detect_shell() -> str:
        if shutil.which("fish"):
            return "fish"
        env_shell = os.environ.get("SHELL")
        if env_shell and shutil.which(env_shell):
            return env_shell
        for candidate in ["zsh", "bash", "sh"]:
            if shutil.which(candidate):
                return candidate
        return "sh"

    def exit_session(self) -> str:
        return self.dispatch("hl.dsp.exit()")

    @staticmethod
    def _get_self_ancestor_pids() -> Set[int]:
        ancestors = set()
        try:
            pid = os.getpid()
            while pid > 1:
                ancestors.add(pid)
                with open(f"/proc/{pid}/stat", "r") as f:
                    stat = f.read().split()
                    pid = int(stat[3])
        except Exception:
            pass
        return ancestors

    def _get_window_descendants(self, root_pid: int) -> List[str]:
        if not root_pid or root_pid <= 1:
            return []
        parent_map: Dict[int, List[int]] = {}
        proc_info: Dict[int, str] = {}
        proc_cmdlines: Dict[int, str] = {}
        try:
            import glob
            for p_dir in glob.glob("/proc/[0-9]*"):
                try:
                    pid = int(os.path.basename(p_dir))
                    with open(f"{p_dir}/stat", "r") as f:
                        stat = f.read().split()
                        comm = stat[1].strip("()")
                        ppid = int(stat[3])
                        parent_map.setdefault(ppid, []).append(pid)
                        proc_info[pid] = comm.lower()
                    with open(f"{p_dir}/cmdline", "rb") as cmdf:
                        cmd_str = cmdf.read().decode("utf-8", errors="ignore").replace("\x00", " ").lower()
                        proc_cmdlines[pid] = cmd_str
                except Exception:
                    continue
        except Exception:
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

    def get_self_window(self) -> Optional[Dict[str, Any]]:
        ancestors = self._get_self_ancestor_pids()
        clients = self.get_clients()
        for c in clients:
            if c.get("pid") in ancestors:
                return c
        return None

    def resolve_window(self, target: str) -> Optional[Dict[str, Any]]:
        target_clean = str(target).strip()
        if not target_clean:
            return None
        target_lower = target_clean.lower()

        if target_lower in ("active", "active window", "active_window", "focused", "focused window", "focused_window", "current", "current window", "current_window"):
            act_win = self.get_active_window()
            if act_win:
                return act_win

        self_keywords = ("textile", "weave", "twill", "agy", "agy_cli", "self", "you", "yourself", "this", "this window", "my window", "your window", "here")
        if target_lower in self_keywords:
            self_win = self.get_self_window()
            if self_win:
                return self_win

        clients = self.get_clients()
        if not clients:
            return None

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

        keywords = [w for w in target_lower.split() if w]
        is_querying_self = any(k in target_lower for k in self_keywords)
        self_ancestors = self._get_self_ancestor_pids()

        scored_clients = []
        for c in clients:
            score = 0
            title = c.get("title", "").lower()
            cls_name = c.get("class", "").lower()
            init_cls = c.get("initialClass", "").lower()
            init_title = c.get("initialTitle", "").lower()
            addr = c.get("address", "").lower()
            pid = c.get("pid", 0)
            is_self_window = pid in self_ancestors

            if target_lower in addr or target_lower == addr:
                return c

            child_procs = self._get_window_descendants(pid)
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

            if score > 0:
                focus_hist = c.get("focusHistoryID", 99)
                if isinstance(focus_hist, int):
                    score += max(0, 10 - focus_hist)
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
            return self.dispatch(f'hl.dsp.focus({{ window = "address:{win["address"]}" }})')
        return f"Error: No open window found matching '{target_clean}'."

    def close_window(self, target: Optional[str] = None) -> str:
        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if win and "address" in win:
                return self.dispatch(f'hl.dsp.window.close({{ window = "address:{win["address"]}" }})')
            return f"Error: No open window found matching '{target_clean}'."
        return self.dispatch("hl.dsp.window.close()")

    def move_to_workspace(self, workspace: str, target: Optional[str] = None, silent: bool = False) -> str:
        ws_str = str(workspace).strip()
        current_ws = None
        if silent:
            act = self.get_active_workspace()
            current_ws = act.get("name") or act.get("id")

        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if win and "address" in win:
                res = self.dispatch(f'hl.dsp.window.move({{ window = "address:{win["address"]}", workspace = "{ws_str}" }})')
                if silent and current_ws:
                    self.focus_workspace(str(current_ws))
                return res
            return f"Error: No open window found matching '{target_clean}'."

        res = self.dispatch(f'hl.dsp.window.move({{ workspace = "{ws_str}" }})')
        if silent and current_ws:
            self.focus_workspace(str(current_ws))
        return res

    def window_action(self, action: str, target: Optional[str] = None) -> str:
        act = action.lower().strip()
        if act in ("close", "kill"):
            return self.close_window(target=target)

        win_param = ""
        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if not win or "address" not in win:
                return f"Error: No open window found matching '{target_clean}'."
            win_param = f', window = "address:{win["address"]}"'

            if act in ("fullscreen", "toggle_fullscreen"):
                self.dispatch(f'hl.dsp.focus({{ window = "address:{win["address"]}" }})')
                return self.dispatch(f'hl.dsp.window.fullscreen({{ mode = "fullscreen", window = "address:{win["address"]}" }})')

        if act in ("float", "togglefloating"):
            return self.dispatch(f"hl.dsp.window.float({{{win_param.lstrip(', ')}}})")
        elif act in ("fullscreen", "toggle_fullscreen"):
            return self.dispatch('hl.dsp.window.fullscreen({ mode = "fullscreen" })')
        elif act == "pin":
            return self.dispatch(f"hl.dsp.window.pin({{{win_param.lstrip(', ')}}})")
        elif act == "center":
            return self.dispatch(f"hl.dsp.window.center({{{win_param.lstrip(', ')}}})")
        else:
            return self.dispatch(f"hl.dsp.window.{act}({{{win_param.lstrip(', ')}}})")

    def focus_direction(self, direction: str) -> str:
        dir_clean = direction.lower().strip()
        return self.dispatch(f'hl.dsp.focus({{ direction = "{dir_clean}" }})')

    def move_window(
        self,
        delta_x: int = 0,
        delta_y: int = 0,
        direction: Optional[str] = None,
        relative: bool = True,
        target: Optional[str] = None,
    ) -> str:
        rel_str = "true" if relative else "false"
        win_param = ""
        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if not win or "address" not in win:
                return f"Error: No open window found matching '{target_clean}'."
            win_param = f', window = "address:{win["address"]}"'

        if direction:
            dir_clean = direction.lower().strip()
            return self.dispatch(f'hl.dsp.window.move({{ direction = "{dir_clean}"{win_param} }})')

        return self.dispatch(f'hl.dsp.window.move({{ x = {int(delta_x)}, y = {int(delta_y)}, relative = {rel_str}{win_param} }})')

    def resize_window(self, delta_x: int = 0, delta_y: int = 0, relative: bool = True, target: Optional[str] = None) -> str:
        rel_str = "true" if relative else "false"
        win_param = ""
        if target and str(target).strip():
            target_clean = str(target).strip()
            win = self.resolve_window(target_clean)
            if not win or "address" not in win:
                return f"Error: No open window found matching '{target_clean}'."
            win_param = f', window = "address:{win["address"]}"'
        return self.dispatch(f'hl.dsp.window.resize({{ x = {int(delta_x)}, y = {int(delta_y)}, relative = {rel_str}{win_param} }})')

    def exec_app(self, app: str, is_tui: bool = False, title: Optional[str] = None) -> str:
        app_clean = app.strip()
        if is_tui:
            term = self._detect_terminal()
            shell = self._detect_shell()
            app_base = app_clean.split()[0]
            title_str = title or app_base
            shell_args = f'{shell} -i -c "{app_clean}"'

            if term == "foot":
                cmd = f'{term} -a {app_base} -T {title_str} {shell_args}'
            elif term in ("kitty", "alacritty", "ghostty"):
                cmd = f'{term} -T {title_str} -- {shell_args}'
            else:
                cmd = f'{term} -e {shell_args}'
        else:
            cmd = app_clean

        escaped_cmd = cmd.replace('\\', '\\\\').replace('"', '\\"')
        return self.dispatch(f'hl.dsp.exec_cmd("{escaped_cmd}")')

    def get_active_workspace(self) -> Dict[str, Any]:
        res = self.send_json("j/activeworkspace")
        return res if isinstance(res, dict) else {}

    def get_workspaces(self) -> List[Dict[str, Any]]:
        res = self.send_json("j/workspaces")
        return res if isinstance(res, list) else []

    def get_active_window(self) -> Dict[str, Any]:
        res = self.send_json("j/activewindow")
        return res if isinstance(res, dict) else {}

    def get_clients(self) -> List[Dict[str, Any]]:
        res = self.send_json("j/clients")
        return res if isinstance(res, list) else []

    def eval_lua(self, lua_code: str) -> str:
        return self.send_raw(f"eval {lua_code}").strip()

    def set_monitor(self, output: str, mode: str, position: str = "0x0", scale: float = 1.25) -> str:
        out_clean = output.strip()
        mode_clean = mode.strip()
        pos_clean = position.strip()
        code = f'hl.monitor({{ output = "{out_clean}", mode = "{mode_clean}", position = "{pos_clean}", scale = {scale} }})'
        res = self.eval_lua(code)
        return f"Monitor '{out_clean}' configured to {mode_clean} at {pos_clean} (scale {scale}): {res}"

    def get_monitors(self) -> List[Dict[str, Any]]:
        res = self.send_json("j/monitors")
        return res if isinstance(res, list) else []

    def read_events(self, timeout: float = 0.1, max_events: int = 20) -> List[Dict[str, str]]:
        import select
        sock_path = self._get_event_socket_path()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.setblocking(False)
        events = []
        try:
            sock.connect(sock_path)
        except BlockingIOError:
            pass
        except Exception as e:
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
                except (BlockingIOError, socket.error):
                    break
        except Exception as e:
            if not events:
                events.append({"event": "error", "data": str(e)})
        finally:
            sock.close()
        return events

    def set_night_light(
        self,
        temperature: int | str | None = None,
        gamma: Optional[float] = None,
        identity: bool = False,
    ) -> Dict[str, Any]:
        hyprsunset_bin = shutil.which("hyprsunset")
        wlsunset_bin = shutil.which("wlsunset")
        if not hyprsunset_bin and not wlsunset_bin:
            return {"success": False, "error": "Neither hyprsunset nor wlsunset is installed."}

        temp_val: Optional[int] = None
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

        subprocess.run(["pkill", "-x", "hyprsunset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-x", "wlsunset"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                time.sleep(0.2)
                running = proc.poll() is None
                return {"success": running, "manager": "hyprsunset", "pid": proc.pid if running else None, "temperature_kelvin": "identity (6500K / off)" if is_ident else temp_val, "gamma": gamma or 1.0, "identity": is_ident}
            except Exception as e:
                return {"success": False, "error": f"Failed to spawn hyprsunset: {e}"}
        else:
            cmd = [wlsunset_bin]
            if is_ident:
                cmd.extend(["-t", "6500", "-T", "6500"])
            elif temp_val is not None:
                cmd.extend(["-t", str(temp_val), "-T", str(temp_val)])
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                time.sleep(0.2)
                running = proc.poll() is None
                return {"success": running, "manager": "wlsunset", "pid": proc.pid if running else None, "temperature_kelvin": "identity (6500K / off)" if is_ident else temp_val, "gamma": gamma or 1.0, "identity": is_ident}
            except Exception as e:
                return {"success": False, "error": f"Failed to spawn wlsunset: {e}"}

    def get_night_light_status(self) -> Dict[str, Any]:
        res_hypr = subprocess.run(["pgrep", "-la", "hyprsunset"], stdout=subprocess.PIPE, text=True)
        res_wl = subprocess.run(["pgrep", "-la", "wlsunset"], stdout=subprocess.PIPE, text=True)
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


class Hyprland(BaseYarn):
    name = "hyprland"
    description = "Direct UNIX Domain Socket IPC for Hyprland Compositor."
    version = "1.1.0"
    layer = LAYER_COMPOSITOR_DE  # Layer 100
    dependencies = [{"type": "env_variable", "target": "HYPRLAND_INSTANCE_SIGNATURE", "optional": True}]

    def is_available(self) -> bool:
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
        if sig:
            return True
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        hypr_dir = os.path.join(runtime, "hypr")
        return os.path.exists(hypr_dir) and bool(os.listdir(hypr_dir)) if os.path.exists(hypr_dir) else False

    def _parse_workspace_target(self, target: str) -> tuple[str, Optional[str]]:
        tokens = target.split()
        if len(tokens) >= 2 and tokens[-1].lstrip("-+").isdigit():
            ws = tokens[-1]
            win_query = " ".join(tokens[:-1])
            return ws, win_query
        return target or "1", None

    @strand(description="Focus a Hyprland window by title, class, address, or search query.")
    def hyprland_focus_window(self, target: str) -> str:
        """Focus a Hyprland window by title, class, address, or search query.

        :param target: Window title, class, address (e.g. 0x12345), or query.
        """
        return hyprland_ipc.focus_window(target)

    @strand(description="Switch active Hyprland workspace.")
    def hyprland_focus_workspace(self, workspace: str = "1") -> str:
        """Switch active Hyprland workspace.

        :param workspace: Workspace ID, name, or relative offset (e.g. '1', 'work', '+1', '-1').
        """
        return hyprland_ipc.focus_workspace(workspace)

    @strand(description="Move target or active window to specified workspace.")
    def hyprland_move_window_to_workspace(
        self,
        workspace: str,
        target: Optional[str] = None,
        silent: bool = False,
    ) -> str:
        """Move target or active window to specified workspace.

        :param workspace: Target workspace ID or name.
        :param target: Window title, class, address, or query. Omit for active window.
        :param silent: If true, do not switch focus to destination workspace.
        """
        ws, win_q = self._parse_workspace_target(f"{target} {workspace}".strip() if target else str(workspace))
        return hyprland_ipc.move_to_workspace(ws, win_q, silent=silent)

    @strand(description="Close a window by query, address, or active window.")
    def hyprland_close_window(self, target: Optional[str] = None) -> str:
        """Close a window by query, address, or active window.

        :param target: Window query or address. Omit to close active window.
        """
        return hyprland_ipc.close_window(target=target)

    @strand(description="Toggle floating state for active or specified window.")
    def hyprland_toggle_float(self, target: Optional[str] = None) -> str:
        """Toggle floating state for active or specified window.

        :param target: Target window query or address.
        """
        return hyprland_ipc.window_action("float", target=target)

    @strand(description="Toggle fullscreen mode for active or specified window.")
    def hyprland_toggle_fullscreen(self, target: Optional[str] = None) -> str:
        """Toggle fullscreen mode for active or specified window.

        :param target: Target window query or address.
        """
        return hyprland_ipc.window_action("fullscreen", target=target)

    @strand(description="Pin window to show across all workspaces.")
    def hyprland_pin_window(self, target: Optional[str] = None) -> str:
        """Pin window to show across all workspaces.

        :param target: Target window query or address.
        """
        return hyprland_ipc.window_action("pin", target=target)

    @strand(description="Center floating window on screen.")
    def hyprland_center_window(self, target: Optional[str] = None) -> str:
        """Center floating window on screen.

        :param target: Target window query or address.
        """
        return hyprland_ipc.window_action("center", target=target)

    @strand(description="Move active or specified window by pixel offset (delta_x, delta_y) or in direction (left, right, up, down).")
    def hyprland_move_window(
        self,
        delta_x: int = 0,
        delta_y: int = 0,
        direction: Optional[Literal["left", "right", "up", "down"]] = None,
        target: Optional[str] = None,
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

    @strand(description="Resize active or specified window by delta X and delta Y.")
    def hyprland_resize_window(
        self,
        delta_x: int,
        delta_y: int,
        target: Optional[str] = None,
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

    @strand(description="Move focus in specified direction (left, right, up, down).")
    def hyprland_focus_direction(
        self,
        direction: Literal["left", "right", "up", "down"] = "left",
    ) -> str:
        """Move focus in specified direction (left, right, up, down).

        :param direction: Direction to move focus.
        """
        return hyprland_ipc.focus_direction(direction)

    @strand(description="Set color temperature for night light / Hyprsunset.")
    def hyprland_set_night_light(self, temperature: int = 4000) -> Dict[str, Any]:
        """Set color temperature for night light / Hyprsunset.

        :param temperature: Color temperature in Kelvin (e.g. 3500, 4000, 6500).
        """
        return hyprland_ipc.set_night_light(temperature=int(temperature))

    @strand(description="Get current night light color temperature and process status.")
    def hyprland_get_night_light(self) -> Dict[str, Any]:
        """Get current night light color temperature and process status."""
        return hyprland_ipc.get_night_light_status()

    @strand(description="Configure Hyprland monitor resolution, position, and scale.")
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

    @strand(description="Get details of currently active workspace.")
    def hyprland_get_active_workspace(self) -> Dict[str, Any]:
        """Get details of currently active workspace."""
        return hyprland_ipc.get_active_workspace()

    @strand(description="Get details of currently focused window.")
    def hyprland_get_active_window(self) -> Dict[str, Any]:
        """Get details of currently focused window."""
        return hyprland_ipc.get_active_window()

    @strand(description="Get window details for the calling Textile / CLI process.")
    def hyprland_get_self_window(self) -> Optional[Dict[str, Any]]:
        """Get window details for the calling Textile / CLI process."""
        return hyprland_ipc.get_self_window()

    @strand(description="List all active Hyprland workspaces.")
    def hyprland_get_workspaces(self) -> List[Dict[str, Any]]:
        """List all active Hyprland workspaces."""
        return hyprland_ipc.get_workspaces()

    @strand(description="Get window details by title, class, address, or query.")
    def hyprland_get_window(self, target: str) -> Dict[str, Any]:
        """Get window details by title, class, address, or query.

        :param target: Window title, class, or address.
        """
        return hyprland_ipc.resolve_window(target) or {"error": f"Window '{target}' not found"}

    @strand(description="List all open windows / clients in Hyprland.")
    def hyprland_get_windows(self) -> List[Dict[str, Any]]:
        """List all open windows / clients in Hyprland."""
        return hyprland_ipc.get_clients()

    @strand(description="List connected monitors and layout geometry.")
    def hyprland_get_monitors(self) -> List[Dict[str, Any]]:
        """List connected monitors and layout geometry."""
        return hyprland_ipc.get_monitors()

    @strand(description="Exit Hyprland compositor session (logout).")
    def hyprland_exit_session(self) -> str:
        """Exit Hyprland compositor session (logout)."""
        return hyprland_ipc.exit_session()

    @strand(
        description="Launch application or shell command via Hyprland exec dispatcher.",
        capability="desktop.app_launcher",
    )
    def hyprland_launch_app(self, command: str) -> str:
        """Launch application or shell command via Hyprland exec dispatcher.

        :param command: Command line or application name to launch.
        """
        return hyprland_ipc.exec_app(app=command)
