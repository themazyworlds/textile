# Textile

A Linux desktop intelligence and automation framework. Textile provides a layered runtime dispatch architecture that exposes Linux system subsystems, Wayland compositors, and desktop protocols to AI agents, Model Context Protocol (MCP) clients, and real-time voice companions.

<p align="center">
  <video src="assets/canvas_showcase.mp4" width="720" controls autoplay loop muted playsinline style="border-radius: 8px;"></video>
</p>

---

## Architecture Overview

Textile organizes desktop capabilities into modular components with priority-based layer dispatch and worker process isolation:

| Concept | Implementation | Description |
|---|---|---|
| **Loom** | Dispatch Engine | Manages runtime tool routing, layer overrides (10 to 150), and subprocess isolation. |
| **Skein** | Discovery Registry | Scans entrypoints, dynamic plugins, and tracks enable/disable state. |
| **Yarn** | Capability Module | Modular domain class (e.g. PackageKit, Polkit, Hyprland, D-Bus). |
| **Strand** | Tool Function | Individual typed function exposed to agents with Pydantic v2 validation. |
| **Weft** | Stream Interceptor | Regex pattern parser for real-time text and speech streams. |
| **Warp** | Event Bus | Asynchronous pub/sub broker for system state and UI events. |
| **Tapestry** | State Blackboard | In-memory key-value ledger for active context and task tracking. |
| **Twill** | MCP Server | Standard Model Context Protocol (stdio) interface for external AI assistants. |
| **Seams** | Health Diagnostics | Dependency auditing and PubGrub conflict resolution engine. |
| **Weave** | Voice Agent | Real-time voice companion integrated with LiveKit and Google Gemini Live API. |

---

## Prerequisites

To use all subsystems, configure the following components:

1. **Google Gemini API Key** (required for Weave voice agent):
   ```bash
   export GOOGLE_API_KEY="your-gemini-api-key"
   ```

2. **LiveKit CLI (`lk`)** (required for Weave interactive console and dev modes):
   ```bash
   curl -sSL https://get.livekit.io/cli | bash
   lk cloud auth
   ```

3. **Quickshell** (optional, required for the desktop avatar UI):
   ```bash
   # Arch Linux / AUR
   paru -S quickshell-git
   ```

---

## CLI Reference

```bash
# Manage yarn registry and lifecycle
uv run textile skein
uv run textile skein disable packagekit
uv run textile skein enable packagekit

# Inspect active strands, parameter schemas, and layer priority
uv run textile loom
uv run textile loom --yarn hyprland

# Run dependency audit and system health checks
uv run textile seams

# View priority layer hierarchy (Layer 150 to Layer 10)
uv run textile layers

# Execute a strand directly
uv run textile call clipboard_set text="Hello from Textile"
uv run textile call clipboard_get
uv run textile call hyprland_focus_workspace workspace="2"

# Control Canvas UI state
uv run textile canvas launch
uv run textile canvas mood thinking
uv run textile canvas talk on
uv run textile canvas close

# Start the Twill MCP server over stdio
uv run textile twill

# Launch the Weave real-time voice agent
uv run textile weave
```

---

## Authoring Yarns

Custom capability modules subclass `BaseYarn`. Functions decorated with `@strand` are automatically registered on the Loom and exposed over MCP:

```python
from typing import Optional
from textile.core.base import BaseYarn, CapabilityTier, strand, LAYER_DESKTOP_PROTOCOL

class MediaPlayerYarn(BaseYarn):
    publisher = "community"
    name = "media_player"
    version = "1.0.0"
    layer = LAYER_DESKTOP_PROTOCOL  # Layer 50

    # Optional: declare isolated runtime dependencies
    python_dependencies = ["mpris2>=1.0.2"]

    @strand(description="Toggle media playback.", tier=CapabilityTier.INTERACT)
    def toggle_playback(self, player: Optional[str] = None) -> str:
        """Toggle media playback.

        :param player: Optional player identifier (e.g., 'spotify').
        """
        return f"Toggled playback on {player or 'default'}"

    @strand(description="Set audio volume level.", tier=CapabilityTier.INTERACT)
    def set_volume(self, level: int) -> str:
        """Set playback volume level.

        :param level: Volume level between 0 and 100.
        """
        return f"Volume set to {level}%"
```

Pydantic v2 validates inputs, coerces types, and generates JSON Schema specifications for MCP clients.

---

## Linux Subsystems and Privilege Management

- **PolicyKit-1 Integration**: Strands can request execution authorization through Polkit rules without spawning interactive dialogs.
- **AT-SPI Accessibility**: Inspect and interact with desktop application widgets, buttons, menus, and text fields via semantic object paths.
- **Compositor IPC**: Direct socket communication for Hyprland window placement, workspace routing, monitor layout, and night light configuration.
- **System and POSIX Primitives**: Safe filesystem operations, kernel inotify directory watches, hardware sensors, and CPU frequency queries.

---

## Canvas Desktop UI

Textile Canvas provides a Wayland overlay UI rendered via QtQuick and Quickshell:

- **17 Preset Mood States**: `neutral`, `happy`, `excited`, `celebrating`, `thinking`, `focused`, `listening`, `curious`, `calm`, `shy`, `mischievous`, `confused`, `surprised`, `alert`, `sleepy`, `error`, `glitch`.
- **Inline Stream Interception**: Weave extracts semantic control tags (`<mood:...>`, `<gaze:x,y>`) from model responses in real time.
- **State Feedback**: Visual cues for voice activity, speech synthesis, and active background execution.
- **Standalone Process**: Runs independently through IPC and can be launched or stopped via the CLI.

---

## Testing

```bash
# Run test suite
uv run pytest

# Run integration diagnostics
uv run python tests/run_all_tests.py

# Build distribution packages
uv build
```

---

## License

Textile is open-source software licensed under the [Apache License 2.0](LICENSE).



