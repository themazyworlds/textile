# Textile Agent Automation & Desktop Intelligence System

This document is the definitive, self-contained reference guide for AI agents interacting with the Linux desktop, GUI applications, and system subsystems via the Textile architecture.


---

## System Architecture Overview

The Textile automation subsystem operates on a layered, protocol-first fabric managed by **Skein**, **Loom**, and **Twill**:

```
┌──────────────────────────────────────────────────────────────────┐
│             Weave Real-Time Voice & AI Agent Engine              │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ Twill (MCP / Stdio JSON-RPC)
┌─────────────────────────────────▼────────────────────────────────┐
│                   Loom (Runtime Dispatch Engine)                 │
│         High-speed in-memory strand execution & layer overrides  │
├──────────────────────────────────────────────────────────────────┤
│                   Skein (Yarn & Lifecycle Manager)               │
│         Discovery, PEP 621 entrypoints, dependency auditing      │
├─────────────────┬────────────────┬─────────────────┬─────────────┤
│  Layer 150      │  Layer 100     │  Layer 50       │  Layer 10   │
│  Session Yarn   │  Compositor    │  Protocol Yarns │  Core POSIX │
│  (UWSM)         │  (Hyprland)    │  (AT-SPI, D-Bus)│  (FS, Proc) │
└─────────────────┴────────────────┴─────────────────┴─────────────┘
```

1. **`Skein` (Lifecycle & Discovery)**: Recursively discovers built-in yarns in individual directories (`src/textile/yarns/<yarn_name>/`), PEP 621 entrypoints (`textile.yarns`), and user custom yarns (`~/.config/textile/yarns`). Manages configuration persistence, intent compilation, and runtime availability checks.
2. **`Loom` (Runtime Dispatcher)**: High-speed live execution engine resolving priority layer overrides (`150` ➔ `10`), origin token validation, and multi-process crash isolation.
3. **`Twill` (Protocol Fabric)**: Standard Model Context Protocol (MCP) server dynamically aggregating all active Strands.
4. **`Weave` (Voice Agent Engine)**: Full-duplex live audio, vision, and real-time conversation companion with semantic mood tag integration.
5. **`Strands` (Tools & Actions)**: Individual callable operations written with Pydantic v2 `@strand` decorators across fabric layers:
   - **Layer 150 (Session Lifecycle)**: `uwsm_status`, `uwsm_stop`, `uwsm_finalize`.
   - **Layer 100 (Compositor & Canvas)**: `hyprland_dispatch`, `hyprland_focus_window`, `caelestia_*`, `canvas_*`.
   - **Layer 50 (Semantic Protocols)**: `atspi_*`, `polkit_*`, `dbus_*`, `clipboard_*`, `ydotool_*`, `journal_*`.
   - **Layer 10 (Core POSIX)**: `file_*`, `inotify_*`, `process_*`, `sensors_*`, `packagekit_*`, `run_command`, `search_web`, `fetch_webpage`, `capture_screen`.


### Yarn Directory Layout

Every yarn lives in its own self-contained directory under `src/textile/yarns/`:

```
src/textile/yarns/
├── atspi/           # AT-SPI accessibility protocol yarn & AT-SPI tree parser
├── basics/          # Core web search, webpage fetch, and basic utilities yarn
├── caelestia/       # Caelestia shell UI launcher & sidebar control yarn
├── canvas/          # Quickshell Canvas QML UI, emotive state, and mood yarn
├── clipboard/       # Wayland/X11 zero-dependency clipboard manager yarn
├── dbus_system/     # D-Bus system & session bus introspection and dispatch yarn
├── filesystem/      # POSIX atomic file operations & Linux inotify monitoring yarn
├── hyprland/        # Hyprland socket IPC compositor control & workspace yarn
├── journal/         # Systemd journald log querying and filtering yarn
├── packagekit/      # PackageKit D-Bus package management yarn
├── process/         # POSIX process management & session process guard yarn
├── screen_vision/   # Screenshot capture & OCR screen vision yarn
├── sensors/         # Hardware temperature & power telemetry yarn
├── uwsm/            # UWSM session & systemd user scope management yarn
├── weave/           # LiveKit full-duplex Voice AI companion agent yarn
├── web_research/    # Web research & scraping tools yarn
└── ydotool/         # uinput synthetic input injection yarn
```


---

## Security Architecture & Policy Enforcement

Textile implements a unified security model across all execution paths.

### 1. Single-Source-of-Truth Policy Gate (`verify_security_policy`)
Policy checks are defined strictly in `src/textile/core/context.py` via `verify_security_policy()`. Both `Loom.execute()` (MCP tool execution) and `Skein.compile_and_execute_intent()` (declarative intent DAG execution) delegate to this function, guaranteeing identical security rules regardless of how a tool is invoked.

- **Capability Tiers**: `OBSERVE` (0), `MUTATE_LOCAL` (1), `PRIVILEGED` (2), `SYSTEM_EXEC` (3).
- **Origin Tokens**: Identify request origins (`LOCAL_DISPLAY`, `VOICE_SESSION`, `MCP_REMOTE`, `UNTRUSTED_IPC`) and carry associated `TrustLevel` (`FULL`, `MEDIUM`, `LOW`, `NONE`).
- **Policy Enforcement**: `MUTATE_LOCAL` or higher tiers require authenticated tokens (`TrustLevel.FULL` or `TrustLevel.MEDIUM`). Untrusted requests (`TrustLevel.NONE`) trigger `PolicyViolationError`.

### 2. Isolated Execution Sandboxes (`Desks` & `Sandbox`)
- **Isolated Workspace**: `src/textile/core/sandbox.py` standardizes temporary sandbox directory creation using `tempfile.gettempdir()` for robust cross-platform temporary workspace management.
- **Resource Catalog (`KNOWN_RESOURCES`)**: Named resource catalog mapping explicit IPC socket dependencies (`dbus-session`, `dbus-system`, `display`, `sound`) without broad host filesystem mounts.


---

## PolicyKit-1 & Privilege Escalation (`polkit_*`)

Textile owns its full privilege lifecycle without hardcoded hacks.

### Active System Pre-Authorization Rule
The system has active pre-authorization rules configured in `/etc/polkit-1/rules.d/10-textile-automation.rules` for user `mazy`:
- **`pkexec` CLI Elevation (`org.freedesktop.policykit.exec`)**: Pre-authorized with `Result.YES`. `polkit_pkexec` executes privileged root commands instantly with **zero password prompts**.
- **Systemd Units (`org.freedesktop.systemd1.*`)**: Starting, stopping, and restarting services runs silently without UI dialogs.
- **Power & Session (`org.freedesktop.login1.*`)**: Power management, reboots, and session control are pre-authorized.
- **Network & Bluetooth (`org.freedesktop.NetworkManager.*`, `org.bluez.*`)**: Network state and Bluetooth pairing are pre-authorized.
- **Textile Vendor Actions (`com.textile.*`)**: Registered under `/usr/share/polkit-1/actions/com.textile.policy`.

| Tool | Purpose | Example Call |
|---|---|---|
| `polkit_check_auth` | Query authority whether process is authorized for an action | `polkit_check_auth(action_id="org.freedesktop.systemd1.manage-units")` |
| `polkit_list_actions` | Search system-wide action definitions and implicit defaults | `polkit_list_actions(filter_query="systemd")` |
| `polkit_generate_policy` | Generate custom `.policy` XML files with Textile vendor identity | `polkit_generate_policy(actions='[{"id":"com.textile.system.restart-service", "description":"Restart service"}]')` |
| `polkit_generate_rule` | Generate JavaScript `.rules` for passwordless / automated authorization | `polkit_generate_rule(rule_name="Textile Rule", action_pattern="com.textile.system.*", users='["mazy"]', result="yes")` |
| `polkit_pkexec` | Execute one-off privileged CLI subprocesses with instant elevation | `polkit_pkexec(command="systemctl restart bluetooth")` |

---

## Textile State & System Health

Textile maintains real-time state and diagnostics:

| Tool | Purpose | Key Parameters |
|---|---|---|
| `textile_get_state` | Read active layers, mood, tool invocations, & configuration | (none) |
| `audit_yarn_integrity` | Perform system-wide integrity and health audit of all yarns and strands | (none) |
| `run_system_tests` | Run the full test suite and return pass/fail report | (none) |
| `cancel_live_task` | Cancel an active live background task | `strand_name` |

---

## Universal Linux Semantic GUI Automation (`atspi_*`)

AT-SPI provides direct, protocol-level control over all graphical elements.

### Available Tools

| Tool | Purpose | Example Call |
|---|---|---|
| `atspi_list_apps` | List all running GUI applications on the a11y bus | `atspi_list_apps()` |
| `atspi_get_tree` | Dump accessible hierarchy of an app | `atspi_get_tree(app_name="safeeyes", max_depth=5)` |
| `atspi_find_elements` | Search elements by query, role, or state | `atspi_find_elements(app_name="safeeyes", query="long break", role="spin button")` |
| `atspi_get_focused` | Retrieve current focused widget | `atspi_get_focused()` |
| `atspi_do_action` | Trigger native action (click, toggle, activate) | `atspi_do_action(app_name="safeeyes", element_name="Breaks")` |
| `atspi_select` | Select tab, list item, or dropdown option | `atspi_select(app_name="pavucontrol", element_name="Profile:", index=1)` |
| `atspi_set_value` | Set value on slider or progress bar | `atspi_set_value(app_name="pavucontrol", element_name="Volume", value=75.0)` |
| `atspi_set_text` | Replace text in entry, spin button, or password dialog | `atspi_set_text(text="60", app_name="safeeyes", element_name="long break interval")` |
| `atspi_insert_text` | Insert text at specific character index | `atspi_insert_text(text="hello", position=-1, app_name="editor")` |
| `atspi_generate_key` | Synthesize keypress, hotkey combo, or string | `atspi_generate_key(combo="ctrl+c")` |
| `atspi_click_element`| Coordinate-accurate synthetic mouse click | `atspi_click_element(app_name="safeeyes", element_name="Close")` |
| `atspi_get_element_bounds` | Retrieve widget bounds & screen center coordinates | `atspi_get_element_bounds(app_name="safeeyes", element_name="Settings")` |

---

## Universal UI Interaction Recipes

### 1. Modifying Numerical Inputs & Spin Buttons (e.g., Safe Eyes, GIMP)
GTK/Qt spin buttons often have blank names (`name=""`) with descriptive labels in preceding sibling widgets and section headers in parent containers.
- **How to target**: Use natural query names. The engine automatically synthesizes contextual names like `"Long Breaks: Interval between two breaks (in minutes)"`.
- **How to change**: Call `atspi_set_text`:
  ```python
  atspi_set_text(text="60", app_name="safeeyes", element_name="long break interval")
  ```

### 2. Toggling Switches & Checkboxes
- **How to target**: Search by switch label or section context.
- **How to toggle**: Call `atspi_do_action`:
  ```python
  atspi_do_action(app_name="safeeyes", element_name="Strict break", action_name="toggle")
  ```

### 3. Interacting with Dropdown Menus & Combo Boxes (e.g., Pavucontrol, Control Center)
Modern GTK4 `GtkDropDown` and `GtkComboBox` widgets wrap an internal toggle button and implement the AT-SPI `Selection` interface directly on the container.
- **To Open the Dropdown**: Call `atspi_do_action` (automatically delegates to the internal toggle button):
  ```python
  atspi_do_action(app_name="pavucontrol", element_name="Profile:")
  ```
- **To Select an Option by Index**: Call `atspi_select`:
  ```python
  atspi_select(app_name="pavucontrol", element_name="Profile:", index=1)
  ```

### 4. Navigating Page Tabs & Tab Lists
- **How to switch tabs**: Call `atspi_do_action` or `atspi_select` with the tab's exact name. If the tab list uses standard selection protocol, the engine routes directly to `Parent.Selection.select_child`:
  ```python
  atspi_do_action(app_name="safeeyes", element_name="Settings")
  atspi_do_action(app_name="safeeyes", element_name="Breaks")
  atspi_do_action(app_name="safeeyes", element_name="Plugins")
  ```

### 5. Automated Privilege Escalation via Polkit + D-Bus
When triggering privileged system operations over D-Bus (such as `systemd` unit restarts):
1. **Execute D-Bus call**: `dbus_call(bus="system", destination="org.freedesktop.systemd1", path="/org/freedesktop/systemd1", interface="org.freedesktop.systemd1.Manager", method="RestartUnit", signature="ss", args='["bluetooth.service", "replace"]')`.
2. **Interactive Polkit Authentication**: The D-Bus layer automatically includes `ALLOW_INTERACTIVE_AUTHORIZATION`, popping up the native authentication dialog.
3. **Automate Password Entry**:
   ```python
   atspi_set_text(text="<password>", app_name="polkit", press_enter=True)
   ```

---

## Window Management & Compositor Control (`hyprland_*`)

Direct Hyprland socket IPC for window, workspace, and layout management:

```python
# Focus window by title or application class
hyprland_focus_window(window="safeeyes")
hyprland_focus_window(window="class:foot")

# Manage workspaces
hyprland_focus_workspace(workspace="2")
hyprland_move_window_to_workspace(workspace="2", silent=False)  # Move active window to workspace 2
hyprland_move_window_to_workspace(workspace="4", window="firefox", silent=True)  # Move window silently

# Window geometry & movement
hyprland_move_window(direction="right")
hyprland_resize_window(dx=50, dy=0)
hyprland_toggle_fullscreen()
hyprland_toggle_float()
hyprland_close_window()

# Blue Light Filter / Color Temperature (hyprsunset)
hyprland_set_night_light(temperature="4000")  # Warm evening light
hyprland_set_night_light(temperature="3000")  # Candle / deep night
hyprland_set_night_light(temperature="off")   # Reset to normal daytime (identity)
hyprland_get_night_light()                 # Check active status & PID
```

---

## POSIX Process, Filesystem & Kernel Monitoring

- **`inotify_*` (Linux Kernel Real-Time Filesystem Monitoring)**:
  - Add Watch: `inotify_watch(path="/path/to/dir", events="create,modify,delete,move", recursive=True)`
  - Wait for Event: `inotify_wait_event(path="/path/to/build/output.bin", events="create", timeout_seconds=10.0)`
  - Read Events: `inotify_read_events(timeout_ms=100, max_events=50)`
  - List Active Watches: `inotify_list_watches()`
  - Remove Watch: `inotify_unwatch(watch=1)` or `inotify_unwatch(watch="/path/to/dir")`

- **`file_op` (Atomic Filesystem Operations & inotify)**:
  - Basic I/O: `file_op(operation="read" | "write" | "replace" | "list" | "find" | "stat" | "chmod" | "disk_usage", path="...")`
  - Integrated inotify: `file_op(operation="watch" | "wait_event" | "read_events" | "unwatch" | "list_watches", path="...")`

- **`launch_app(app="firefox", is_tui=False)`**: Launch GUI or terminal-native applications.
- **`process_action(action="kill", pid=1234, signal="SIGTERM")`**: Send POSIX signals.
- **`wait_delay(seconds=3)`**: Async execution pacing between UI actions.
