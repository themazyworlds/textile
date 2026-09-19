"""
Native AT-SPI Accessibility Capability Yarn for Textile.
Provides direct semantic access to Linux GUI applications (GTK, Qt, Electron, Chromium, Firefox)
via D-Bus a11y hierarchy.
Layer 50 (Desktop Protocol).
"""

import json
import logging
import os
import sys
import time
import warnings
from typing import Any, Dict, List, Literal, Optional

from textile.core.base import BaseYarn, strand, LAYER_DESKTOP_PROTOCOL

logger = logging.getLogger("textile.yarns.protocols.atspi")


_ATSPI_INITIALIZED = False
_ATSPI_AVAILABLE = False

for _p in [
    "/usr/lib/python3.14/site-packages",
    "/usr/lib64/python3.14/site-packages",
    "/usr/lib/python3.13/site-packages",
    "/usr/lib64/python3.13/site-packages",
    "/usr/lib/python3.12/site-packages",
    "/usr/lib/python3/dist-packages",
    "/usr/local/lib/python3.14/site-packages",
]:
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.append(_p)

try:
    import warnings
    import gi
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*unix_signal_add_full.*")
        warnings.filterwarnings("ignore", message=".*GLib.*deprecated.*")
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    _ATSPI_AVAILABLE = True
except Exception as e:
    _ATSPI_AVAILABLE = False
    logger.debug(f"AT-SPI not available on this environment: {e}")

_GDK_KEYVAL_FUNC = None
try:
    if _ATSPI_AVAILABLE:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*unix_signal_add_full.*")
            warnings.filterwarnings("ignore", message=".*GLib.*deprecated.*")
            try:
                gi.require_version("Gdk", "4.0")
            except Exception:
                try:
                    gi.require_version("Gdk", "3.0")
                except Exception:
                    pass
            from gi.repository import Gdk
            _GDK_KEYVAL_FUNC = Gdk.keyval_from_name
except Exception:
    _GDK_KEYVAL_FUNC = None

KNOWN_KEYVALS: Dict[str, int] = {
    "enter": 65293, "return": 65293, "tab": 65289, "escape": 65307, "esc": 65307,
    "backspace": 65288, "delete": 65535, "del": 65535, "insert": 65379, "space": 32,
    "spacebar": 32, "up": 65362, "down": 65364, "left": 65361, "right": 65363,
    "home": 65360, "end": 65367, "pageup": 65365, "pagedown": 65366, "ctrl": 65507,
    "alt": 65513, "shift": 65505, "super": 65515, "capslock": 65509,
    "f1": 65470, "f2": 65471, "f3": 65472, "f4": 65473, "f5": 65474, "f6": 65475,
    "f7": 65476, "f8": 65477, "f9": 65478, "f10": 65479, "f11": 65480, "f12": 65481,
}


def _safe_get_name(acc: Any) -> str:
    try:
        return acc.get_name() or ""
    except Exception:
        return ""


def _safe_get_role(acc: Any) -> str:
    try:
        return acc.get_role_name() or "unknown"
    except Exception:
        return "unknown"


def _safe_get_description(acc: Any) -> str:
    try:
        return acc.get_description() or ""
    except Exception:
        return ""


def _safe_child_count(acc: Any) -> int:
    try:
        return acc.get_child_count()
    except Exception:
        return 0


def _safe_get_child(acc: Any, index: int) -> Optional[Any]:
    try:
        return acc.get_child_at_index(index)
    except Exception:
        return None


class AtspiAPI:
    """Native AT-SPI Accessibility API Controller."""

    def __init__(self):
        # Lazy initialization; do not connect to accessibility daemon at module import time
        pass

    def _ensure_init(self) -> bool:
        global _ATSPI_INITIALIZED
        if not _ATSPI_AVAILABLE:
            return False
        if not _ATSPI_INITIALIZED:
            try:
                if hasattr(Atspi, "init") and callable(getattr(Atspi, "init")):
                    Atspi.init()
                _ATSPI_INITIALIZED = True
            except Exception as e:
                logger.debug(f"Failed to initialize AT-SPI: {e}")
                return False
        return _ATSPI_INITIALIZED

    def is_available(self) -> bool:
        return _ATSPI_AVAILABLE and self._ensure_init()

    def _get_active_state_nicks(self, acc: Any) -> List[str]:
        try:
            stateset = acc.get_state_set()
            states_list = stateset.get_states()
            nicks = []
            for st in states_list:
                try:
                    nick = st.value_nick if hasattr(st, "value_nick") else str(st).split(".")[-1].lower()
                    nicks.append(nick)
                except Exception:
                    pass
            return nicks
        except Exception:
            return []

    def _get_bounds(self, acc: Any) -> Optional[Dict[str, int]]:
        try:
            if not acc.is_component():
                return None
            rect = acc.get_extents(Atspi.CoordType.SCREEN)
            if rect.x != 0 or rect.y != 0 or (rect.width > 0 and rect.height > 0):
                if rect.width > 0 and rect.height > 0:
                    return {
                        "x": int(rect.x), "y": int(rect.y), "width": int(rect.width), "height": int(rect.height),
                        "center_x": int(rect.x + rect.width / 2), "center_y": int(rect.y + rect.height / 2), "coord_type": "screen"
                    }
            rect_w = acc.get_extents(Atspi.CoordType.WINDOW)
            if rect_w.width > 0 and rect_w.height > 0:
                return {
                    "x": int(rect_w.x), "y": int(rect_w.y), "width": int(rect_w.width), "height": int(rect_w.height),
                    "center_x": int(rect_w.x + rect_w.width / 2), "center_y": int(rect_w.y + rect_w.height / 2), "coord_type": "window"
                }
        except Exception:
            pass
        return None

    def _get_actions(self, acc: Any) -> List[str]:
        actions = []
        if not acc.is_action():
            return actions
        try:
            n_actions = acc.get_n_actions()
            for i in range(n_actions):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", DeprecationWarning)
                        name = acc.get_action_name(i)
                    if name:
                        actions.append(name)
                except Exception:
                    pass
        except Exception:
            pass
        return actions

    def _get_text(self, acc: Any) -> Optional[str]:
        try:
            if not acc.is_text():
                return None
            char_count = acc.get_character_count()
            if char_count > 0:
                return Atspi.Text.get_text(acc, 0, min(char_count, 2000))
        except Exception:
            pass
        return None

    def _get_value_info(self, acc: Any) -> Optional[Dict[str, Any]]:
        try:
            if not acc.is_value():
                return None
            return {
                "current": float(acc.get_current_value()),
                "minimum": float(acc.get_minimum_value()),
                "maximum": float(acc.get_maximum_value()),
                "step": float(acc.get_minimum_increment()),
            }
        except Exception:
            pass
        return None

    def _infer_context(self, acc: Any) -> tuple[str, str]:
        label_text, section_text = "", ""
        try:
            parent = acc.get_parent()
            if parent:
                idx = acc.get_index_in_parent()
                for i in range(idx - 1, -1, -1):
                    sib = parent.get_child_at_index(i)
                    if sib and sib.get_role_name() == "label":
                        txt = self._get_text(sib) or _safe_get_name(sib)
                        if txt:
                            label_text = txt
                            break
                curr = parent
                for _ in range(4):
                    if not curr:
                        break
                    for i in range(_safe_child_count(curr)):
                        c = _safe_get_child(curr, i)
                        if c and _safe_get_role(c) == "label" and c != acc:
                            txt = self._get_text(c) or _safe_get_name(c)
                            if txt and txt != label_text:
                                section_text = txt
                                break
                    if section_text:
                        break
                    curr = curr.get_parent()
        except Exception:
            pass
        return label_text, section_text

    def _serialize_element(
        self, acc: Any, path: str = "", include_bounds: bool = True, include_actions: bool = True
    ) -> Dict[str, Any]:
        name = _safe_get_name(acc)
        role = _safe_get_role(acc)
        description = _safe_get_description(acc)
        states = self._get_active_state_nicks(acc)
        text = self._get_text(acc)

        labeled_by, section = "", ""
        if not name or role in ("spin button", "switch", "entry", "check box", "combo box", "slider"):
            labeled_by, section = self._infer_context(acc)
            if not name:
                if section and labeled_by:
                    name = f"{section}: {labeled_by}"
                elif labeled_by:
                    name = labeled_by

        data: Dict[str, Any] = {"name": name, "role": role, "path": path, "states": states}
        if labeled_by:
            data["labeled_by"] = labeled_by
        if section:
            data["section"] = section
        if description:
            data["description"] = description
        if text:
            data["text"] = text
        if include_bounds:
            bounds = self._get_bounds(acc)
            if bounds:
                data["bounds"] = bounds
        if include_actions:
            actions = self._get_actions(acc)
            if actions:
                data["actions"] = actions
        val_info = self._get_value_info(acc)
        if val_info:
            data["value"] = val_info
        if acc.is_editable_text():
            data["is_editable"] = True
        if acc.is_selection() or "selectable" in states:
            data["is_selectable"] = True
            data["is_selected"] = "selected" in states
        return data

    def list_applications(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        apps = []
        try:
            desktop = Atspi.get_desktop(0)
            if not desktop:
                return []
            count = _safe_child_count(desktop)
            for i in range(count):
                app = _safe_get_child(desktop, i)
                if not app:
                    continue
                try:
                    name = _safe_get_name(app) or f"App_{i}"
                    pid = app.get_process_id()
                    child_count = _safe_child_count(app)
                    try:
                        toolkit = app.get_toolkit_name() or "unknown"
                    except Exception:
                        toolkit = "unknown"
                    apps.append({"index": i, "name": name, "process_id": pid, "windows_count": child_count, "toolkit": toolkit})
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Error listing AT-SPI applications: {e}")
        return apps

    def _find_app(self, app_name_or_index: Any) -> Optional[Any]:
        if not self.is_available():
            return None
        desktop = Atspi.get_desktop(0)
        if not desktop:
            return None
        count = _safe_child_count(desktop)
        if isinstance(app_name_or_index, int) or (isinstance(app_name_or_index, str) and app_name_or_index.isdigit()):
            idx = int(app_name_or_index)
            if 0 <= idx < count:
                return _safe_get_child(desktop, idx)

        app_name_str = str(app_name_or_index).lower().strip()
        for i in range(count):
            app = _safe_get_child(desktop, i)
            if app:
                name = _safe_get_name(app).lower()
                if app_name_str in name:
                    return app
        return None

    def get_tree(self, app_name: Optional[str] = None, max_depth: int = 3, include_bounds: bool = True) -> Dict[str, Any]:
        if not self.is_available():
            return {"error": "AT-SPI is not available."}
        if app_name:
            target_node = self._find_app(app_name)
            if not target_node:
                return {"error": f"Application '{app_name}' not found."}
            root_path = f"app:{_safe_get_name(target_node)}"
        else:
            target_node = Atspi.get_desktop(0)
            if not target_node:
                return {"error": "Could not access AT-SPI desktop."}
            root_path = "0"

        def _traverse(node: Any, current_path: str, depth: int) -> Dict[str, Any]:
            node_dict = self._serialize_element(node, path=current_path, include_bounds=include_bounds, include_actions=True)
            if depth < max_depth:
                children = []
                try:
                    c_count = _safe_child_count(node)
                    for c_idx in range(c_count):
                        child = _safe_get_child(node, c_idx)
                        if child:
                            children.append(_traverse(child, f"{current_path}/{c_idx}", depth + 1))
                except Exception:
                    pass
                if children:
                    node_dict["children"] = children
            return node_dict

        return _traverse(target_node, root_path, depth=0)

    def find_elements(
        self, query: Optional[str] = None, role: Optional[str] = None, app_name: Optional[str] = None, state: Optional[str] = None, max_results: int = 50, max_depth: int = 15
    ) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        results: List[Dict[str, Any]] = []
        target_root = self._find_app(app_name) if app_name else Atspi.get_desktop(0)
        if not target_root:
            return []

        q_lower = query.lower().strip() if query else None
        role_lower = role.lower().strip() if role else None
        state_lower = state.lower().strip() if state else None

        def _search(node: Any, path: str, depth: int):
            if len(results) >= max_results or depth > max_depth:
                return
            try:
                serialized = self._serialize_element(node, path=path, include_bounds=True, include_actions=True)
                s_name = (serialized.get("name") or "").lower()
                s_role = (serialized.get("role") or "").lower()
                s_desc = (serialized.get("description") or "").lower()
                s_text = (serialized.get("text") or "").lower()
                s_lbl = (serialized.get("labeled_by") or "").lower()
                s_sec = (serialized.get("section") or "").lower()
                states = serialized.get("states", [])

                match_query = True
                if q_lower:
                    combined = f"{s_name} {s_desc} {s_text} {s_lbl} {s_sec}".lower()
                    if q_lower in combined:
                        match_query = True
                    else:
                        q_words = [w.strip("s:-,.()") for w in q_lower.split() if len(w.strip("s:-,.()")) > 1]
                        match_query = bool(q_words and all(w in combined for w in q_words))

                match_role = True
                if role_lower:
                    match_role = role_lower in s_role

                match_state = True
                if state_lower:
                    match_state = state_lower in states

                if match_query and match_role and match_state:
                    results.append(serialized)

                c_count = _safe_child_count(node)
                for i in range(c_count):
                    child = _safe_get_child(node, i)
                    if child:
                        _search(child, f"{path}/{i}", depth + 1)
                        if len(results) >= max_results:
                            break
            except Exception:
                pass

        root_label = f"app:{_safe_get_name(target_root)}" if app_name else "0"
        _search(target_root, root_label, depth=0)
        return results

    def _resolve_element_by_path(self, path: str) -> Optional[Any]:
        if not self.is_available() or not path:
            return None
        parts = path.strip().split("/")
        root_part = parts[0]

        if root_part.startswith("app:"):
            current = self._find_app(root_part[4:])
        elif root_part == "0" or root_part.isdigit():
            current = Atspi.get_desktop(0)
            if root_part != "0":
                current = _safe_get_child(current, int(root_part))
        else:
            current = self._find_app(root_part)

        if not current:
            return None

        for p in parts[1:]:
            if not p.isdigit():
                continue
            idx = int(p)
            if idx < 0 or idx >= _safe_child_count(current):
                return None
            current = _safe_get_child(current, idx)
            if not current:
                return None
        return current

    def get_focused_element(self) -> Optional[Dict[str, Any]]:
        matches = self.find_elements(state="focused", max_results=1)
        if matches:
            return matches[0]
        active_matches = self.find_elements(state="active", max_results=1)
        if active_matches:
            return active_matches[0]
        return None

    def _resolve_target(
        self, element_path: Optional[str] = None, app_name: Optional[str] = None, element_name: Optional[str] = None, preferred_role: Optional[str] = None
    ) -> Optional[Any]:
        if element_path:
            target = self._resolve_element_by_path(element_path)
            if target:
                return target

        if app_name or element_name:
            INTERACTIVE_ROLES = (
                "page tab", "push button", "button", "toggle button", "switch",
                "check box", "radio button", "menu item", "combo box", "entry",
                "spin button", "slider", "list item", "tree table"
            )
            matches = self.find_elements(app_name=app_name, query=element_name, role=preferred_role, max_results=100)
            if matches:
                e_name_clean = (element_name or "").strip().lower()
                for m in matches:
                    m_name = (m.get("name") or "").strip().lower()
                    m_lbl = (m.get("labeled_by") or "").strip().lower()
                    m_role = (m.get("role") or "").strip().lower()
                    if (m_name == e_name_clean or m_lbl == e_name_clean) and m_role in INTERACTIVE_ROLES:
                        return self._resolve_element_by_path(m["path"])

                for m in matches:
                    m_name = (m.get("name") or "").strip().lower()
                    m_lbl = (m.get("labeled_by") or "").strip().lower()
                    if m_name == e_name_clean or m_lbl == e_name_clean:
                        return self._resolve_element_by_path(m["path"])

                for m in matches:
                    m_role = (m.get("role") or "").strip().lower()
                    if m_role in INTERACTIVE_ROLES:
                        return self._resolve_element_by_path(m["path"])

                if "path" in matches[0]:
                    return self._resolve_element_by_path(matches[0]["path"])
        return None

    def do_action(
        self, element_path: Optional[str] = None, app_name: Optional[str] = None, element_name: Optional[str] = None, action_name: Optional[str] = None, action_index: int = 0
    ) -> Dict[str, Any]:
        if not self.is_available():
            return {"success": False, "error": "AT-SPI is not available."}
        target = self._resolve_target(element_path, app_name, element_name)
        if not target:
            return {"success": False, "error": "Element not found."}

        try:
            if target.is_action():
                n_actions = target.get_n_actions()
                chosen_index = action_index
                if action_name and n_actions > 0:
                    for i in range(n_actions):
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", DeprecationWarning)
                            act = (target.get_action_name(i) or "").lower()
                        if action_name.lower() in act:
                            chosen_index = i
                            break
                if n_actions > 0 and chosen_index < n_actions:
                    success = target.do_action(chosen_index)
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", DeprecationWarning)
                        action_performed = target.get_action_name(chosen_index)
                    return {"success": bool(success), "element": _safe_get_name(target), "role": _safe_get_role(target), "action": action_performed}

            try:
                parent = target.get_parent()
                if parent and parent.is_selection():
                    idx = target.get_index_in_parent()
                    res = parent.select_child(idx)
                    return {"success": bool(res), "element": _safe_get_name(target), "role": _safe_get_role(target), "action": "select_child"}
            except Exception:
                pass

            if target.is_component():
                bounds = self._get_bounds(target)
                if bounds and bounds.get("width", 0) > 0:
                    cx, cy = bounds["center_x"], bounds["center_y"]
                    mouse_res = self.generate_mouse_event(cx, cy, "b1c")
                    return {"success": bool(mouse_res), "element": _safe_get_name(target), "role": _safe_get_role(target), "action": "click"}

            return {"success": False, "error": f"Element '{_safe_get_name(target)}' has no actions."}
        except Exception as e:
            return {"success": False, "error": f"Error performing action: {e}"}

    def select_element(self, element_path: Optional[str] = None, app_name: Optional[str] = None, element_name: Optional[str] = None, index: Optional[int] = None) -> Dict[str, Any]:
        if not self.is_available():
            return {"success": False, "error": "AT-SPI is not available."}
        target = self._resolve_target(element_path, app_name, element_name)
        if not target:
            return {"success": False, "error": "Element could not be resolved."}
        try:
            if target.is_selection() and index is not None:
                res = target.select_child(int(index))
                return {"success": bool(res), "element": _safe_get_name(target), "selected_index": index}
            try:
                parent = target.get_parent()
                if parent and parent.is_selection():
                    idx = target.get_index_in_parent()
                    res = parent.select_child(idx)
                    return {"success": bool(res), "element": _safe_get_name(target), "index_in_parent": idx}
            except Exception:
                pass
            return self.do_action(element_path=element_path, app_name=app_name, element_name=element_name)
        except Exception as e:
            return {"success": False, "error": f"Selection error: {e}"}

    def set_value(self, value: float, element_path: Optional[str] = None, app_name: Optional[str] = None, element_name: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_available():
            return {"success": False, "error": "AT-SPI is not available."}
        target = self._resolve_target(element_path, app_name, element_name)
        if not target or not target.is_value():
            return {"success": False, "error": "Element does not implement Value interface."}
        try:
            res = target.set_current_value(float(value))
            return {"success": bool(res) if res is not None else True, "element": _safe_get_name(target), "value_set": float(value)}
        except Exception as e:
            return {"success": False, "error": f"Failed setting value: {e}"}

    def set_text(
        self, text: str, element_path: Optional[str] = None, app_name: Optional[str] = None, element_name: Optional[str] = None, use_focused: bool = True, press_enter: bool = False
    ) -> Dict[str, Any]:
        if not self.is_available():
            return {"success": False, "error": "AT-SPI is not available."}
        target = self._resolve_target(element_path, app_name, element_name)
        if not target and use_focused:
            focused = self.get_focused_element()
            if focused and "path" in focused:
                target = self._resolve_element_by_path(focused["path"])
        if not target:
            return {"success": False, "error": "No editable element found or currently focused."}

        try:
            if target.is_editable_text():
                res = target.set_text_contents(text)
                method_used = "EditableText.set_text_contents"
            else:
                res = self.generate_keyboard_string(text)
                method_used = "synthesized_keyboard_input"
            if press_enter:
                self.generate_key_event(65293, "pressrelease")
            return {"success": bool(res) if res is not None else True, "element": _safe_get_name(target), "text_length": len(text), "method": method_used}
        except Exception as e:
            return {"success": False, "error": f"Failed setting text: {e}"}

    def insert_text(self, text: str, position: int = -1, element_path: Optional[str] = None, app_name: Optional[str] = None, element_name: Optional[str] = None) -> Dict[str, Any]:
        if not self.is_available():
            return {"success": False, "error": "AT-SPI is not available."}
        target = self._resolve_target(element_path, app_name, element_name)
        if not target or not target.is_editable_text():
            return {"success": False, "error": "Element does not implement EditableText."}
        try:
            if position < 0:
                position = target.get_character_count() if target.is_text() else 0
            res = target.insert_text(position, text, len(text))
            return {"success": bool(res) if res is not None else True, "element": _safe_get_name(target), "inserted_at": position}
        except Exception as e:
            return {"success": False, "error": f"Failed inserting text: {e}"}

    def resolve_keyval(self, key_name_or_val: str | int) -> int:
        if isinstance(key_name_or_val, int):
            return key_name_or_val
        k_str = str(key_name_or_val).strip()
        if k_str.isdigit():
            return int(k_str)
        k_lower = k_str.lower()
        if k_lower in KNOWN_KEYVALS:
            return KNOWN_KEYVALS[k_lower]
        if _GDK_KEYVAL_FUNC:
            try:
                kv = _GDK_KEYVAL_FUNC(k_str)
                if kv:
                    return kv
            except Exception:
                pass
        return ord(k_str) if len(k_str) == 1 else 0

    def generate_keyboard_string(self, text: str, press_enter: bool = False) -> bool:
        if not self.is_available():
            return False
        try:
            res = Atspi.generate_keyboard_event(0, text, Atspi.KeySynthType.STRING)
            if press_enter:
                time.sleep(0.05)
                self.generate_key_event(65293, "pressrelease")
            return bool(res)
        except Exception:
            return False

    def generate_key_event(self, key_name_or_val: str | int, event_type: str = "pressrelease") -> bool:
        if not self.is_available():
            return False
        keyval = self.resolve_keyval(key_name_or_val)
        if keyval == 0:
            return False
        type_map = {"press": Atspi.KeySynthType.PRESS, "release": Atspi.KeySynthType.RELEASE, "pressrelease": Atspi.KeySynthType.PRESSRELEASE, "sym": Atspi.KeySynthType.SYM}
        try:
            return bool(Atspi.generate_keyboard_event(keyval, None, type_map.get(event_type.lower(), Atspi.KeySynthType.PRESSRELEASE)))
        except Exception:
            return False

    def generate_key_combo(self, combo: str) -> bool:
        if not self.is_available() or not combo:
            return False
        parts = [p.strip() for p in combo.replace("-", "+").split("+") if p.strip()]
        keyvals = [self.resolve_keyval(p) for p in parts]
        if any(kv == 0 for kv in keyvals):
            return False
        try:
            modifiers, main_key = keyvals[:-1], keyvals[-1]
            for mod in modifiers:
                Atspi.generate_keyboard_event(mod, None, Atspi.KeySynthType.PRESS)
                time.sleep(0.01)
            Atspi.generate_keyboard_event(main_key, None, Atspi.KeySynthType.PRESSRELEASE)
            time.sleep(0.01)
            for mod in reversed(modifiers):
                Atspi.generate_keyboard_event(mod, None, Atspi.KeySynthType.RELEASE)
                time.sleep(0.01)
            return True
        except Exception:
            return False

    def generate_mouse_event(self, x: int, y: int, event_name: str = "b1c") -> bool:
        if not self.is_available():
            return False
        try:
            return bool(Atspi.generate_mouse_event(int(x), int(y), event_name))
        except Exception:
            return False

    def click_element(self, element_path: Optional[str] = None, app_name: Optional[str] = None, element_name: Optional[str] = None, button: str = "left", double_click: bool = False) -> Dict[str, Any]:
        if not self.is_available():
            return {"success": False, "error": "AT-SPI is not available."}
        target = self._resolve_target(element_path, app_name, element_name)
        if not target:
            return {"success": False, "error": "Element not found."}
        bounds = self._get_bounds(target)
        if not bounds or bounds.get("width", 0) <= 0:
            return self.do_action(element_path=element_path, app_name=app_name, element_name=element_name)

        btn_code = "b3c" if button == "right" else ("b2c" if button == "middle" else ("b1d" if double_click else "b1c"))
        res = self.generate_mouse_event(bounds["center_x"], bounds["center_y"], btn_code)
        return {"success": bool(res), "element": _safe_get_name(target), "coordinates": {"x": bounds["center_x"], "y": bounds["center_y"]}}


atspi_api = AtspiAPI()


class Atspi(BaseYarn):
    name = "atspi_a11y"
    description = "Linux AT-SPI Accessibility Interface for semantic UI inspection, native widget actions, and direct text input."
    version = "1.1.0"
    layer = LAYER_DESKTOP_PROTOCOL  # Layer 50
    dependencies = [
        {"type": "python_module", "target": "dbus_fast"},
        {"type": "env_variable", "target": "DBUS_SESSION_BUS_ADDRESS", "optional": True},
    ]

    def is_available(self) -> bool:
        return atspi_api.is_available()

    @strand(description="List all running graphical applications on the Linux AT-SPI accessibility bus.")
    def atspi_list_apps(self) -> Dict[str, Any]:
        """List all running graphical applications on the Linux AT-SPI accessibility bus."""
        apps = atspi_api.list_applications()
        return {"count": len(apps), "applications": apps}

    @strand(description="Retrieve the semantic accessibility element tree of a target application.")
    def atspi_get_tree(
        self,
        app_name: Optional[str] = None,
        max_depth: int = 3,
        include_bounds: bool = True,
    ) -> Dict[str, Any]:
        """Retrieve the semantic accessibility element tree of a target application.

        :param app_name: Application name or substring.
        :param max_depth: Maximum tree depth (default 3).
        :param include_bounds: Include bounding coordinates.
        """
        return atspi_api.get_tree(app_name=app_name, max_depth=max_depth, include_bounds=include_bounds)

    @strand(description="Search for accessible UI elements matching name, role, text content, or state.")
    def atspi_find_elements(
        self,
        query: Optional[str] = None,
        role: Optional[str] = None,
        app_name: Optional[str] = None,
        state: Optional[str] = None,
        max_results: int = 15,
    ) -> Dict[str, Any]:
        """Search for accessible UI elements matching name, role, text content, or state.

        :param query: Search string.
        :param role: Role filter.
        :param app_name: App name filter.
        :param state: State filter.
        :param max_results: Max results (default 15).
        """
        elements = atspi_api.find_elements(
            query=query, role=role, app_name=app_name, state=state, max_results=max_results
        )
        return {"matches_count": len(elements), "elements": elements}

    @strand(description="Get the currently focused accessible UI widget.")
    def atspi_get_focused(self) -> Dict[str, Any]:
        """Get the currently focused accessible UI widget."""
        focused = atspi_api.get_focused_element()
        return {"focused_element": focused}

    @strand(description="Execute a native accessible action (click, press, activate, toggle) on a widget.")
    def atspi_do_action(
        self,
        element_path: Optional[str] = None,
        app_name: Optional[str] = None,
        element_name: Optional[str] = None,
        action_name: Optional[str] = None,
        action_index: int = 0,
    ) -> Dict[str, Any]:
        """Execute a native accessible action (click, press, activate, toggle) on a widget.

        :param element_path: AT-SPI element path.
        :param app_name: Application name.
        :param element_name: Element name.
        :param action_name: Action name.
        :param action_index: Action index.
        """
        return atspi_api.do_action(
            element_path=element_path,
            app_name=app_name,
            element_name=element_name,
            action_name=action_name,
            action_index=action_index,
        )

    @strand(description="Select a tab, radio button, or item from a list.")
    def atspi_select(
        self,
        element_path: Optional[str] = None,
        app_name: Optional[str] = None,
        element_name: Optional[str] = None,
        index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Select a tab, radio button, or item from a list.

        :param element_path: Element path.
        :param app_name: Application name.
        :param element_name: Element name.
        :param index: Child index.
        """
        return atspi_api.select_element(
            element_path=element_path, app_name=app_name, element_name=element_name, index=index
        )

    @strand(description="Directly set or replace the text contents of an editable UI field.")
    def atspi_set_text(
        self,
        text: str,
        element_path: Optional[str] = None,
        app_name: Optional[str] = None,
        element_name: Optional[str] = None,
        use_focused: bool = True,
        press_enter: bool = False,
    ) -> Dict[str, Any]:
        """Directly set or replace the text contents of an editable UI field.

        :param text: Text content to set.
        :param element_path: Element path.
        :param app_name: Application name.
        :param element_name: Element name.
        :param use_focused: Use currently focused input.
        :param press_enter: Press Return after setting text.
        """
        return atspi_api.set_text(
            text=text,
            element_path=element_path,
            app_name=app_name,
            element_name=element_name,
            use_focused=use_focused,
            press_enter=press_enter,
        )

    @strand(description="Insert text at a character offset in an editable widget.")
    def atspi_insert_text(
        self,
        text: str,
        position: int = -1,
        element_path: Optional[str] = None,
        app_name: Optional[str] = None,
        element_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert text at a character offset in an editable widget.

        :param text: String to insert.
        :param position: Character index (-1 for end).
        :param element_path: Element path.
        :param app_name: Application name.
        :param element_name: Element name.
        """
        return atspi_api.insert_text(
            text=text,
            position=position,
            element_path=element_path,
            app_name=app_name,
            element_name=element_name,
        )

    @strand(description="Set the numerical value of a slider, progress bar, or spin box.")
    def atspi_set_value(
        self,
        value: float,
        element_path: Optional[str] = None,
        app_name: Optional[str] = None,
        element_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Set the numerical value of a slider, progress bar, or spin box.

        :param value: Numerical value to set.
        :param element_path: Element path.
        :param app_name: Application name.
        :param element_name: Element name.
        """
        return atspi_api.set_value(
            value=float(value),
            element_path=element_path,
            app_name=app_name,
            element_name=element_name,
        )

    @strand(description="Synthesize keyboard text, single named keys, or hotkey combinations.")
    def atspi_generate_key(
        self,
        text: Optional[str] = None,
        key: Optional[str] = None,
        combo: Optional[str] = None,
        press_enter: bool = False,
    ) -> Dict[str, Any]:
        """Synthesize keyboard text, single named keys, or hotkey combinations.

        :param text: Text string.
        :param key: Key name (e.g. 'Return', 'Tab').
        :param combo: Hotkey string (e.g. 'ctrl+c').
        :param press_enter: Press Return after text.
        """
        if combo:
            success = atspi_api.generate_key_combo(combo)
            return {"success": success, "method": "key_combo", "combo": combo}
        elif key:
            success = atspi_api.generate_key_event(key, event_type="pressrelease")
            return {"success": success, "method": "named_key", "key": key}
        elif text:
            success = atspi_api.generate_keyboard_string(text, press_enter=press_enter)
            return {"success": success, "method": "string_synth", "text": text}
        return {"success": False, "error": "Provide combo, key, or text."}

    @strand(description="Click on an accessible UI element by dispatching a mouse event to its coordinates.")
    def atspi_click_element(
        self,
        element_path: Optional[str] = None,
        app_name: Optional[str] = None,
        element_name: Optional[str] = None,
        button: Literal["left", "right", "middle"] = "left",
        double_click: bool = False,
    ) -> Dict[str, Any]:
        """Click on an accessible UI element by dispatching a mouse event to its coordinates.

        :param element_path: Element path.
        :param app_name: Application name.
        :param element_name: Element name.
        :param button: Mouse button.
        :param double_click: Double click flag.
        """
        return atspi_api.click_element(
            element_path=element_path,
            app_name=app_name,
            element_name=element_name,
            button=button,
            double_click=double_click,
        )

    @strand(description="Get exact screen bounding rectangle for any accessible UI element.")
    def atspi_get_element_bounds(
        self,
        element_path: Optional[str] = None,
        app_name: Optional[str] = None,
        element_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get exact screen bounding rectangle for any accessible UI element.

        :param element_path: Element path.
        :param app_name: Application name.
        :param element_name: Element name.
        """
        matches = atspi_api.find_elements(query=element_name, app_name=app_name, max_results=1)
        if matches and "bounds" in matches[0]:
            return {"element": matches[0].get("name"), "bounds": matches[0].get("bounds")}
        return {"error": "Element bounds not found."}
