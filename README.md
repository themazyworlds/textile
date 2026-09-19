# Textile

https://github.com/user-attachments/assets/291ad11e-f4ad-48ff-933b-03c0285b8933

A modular intelligence and automation framework for Linux. Textile provides a layered runtime dispatch engine and plugin architecture that exposes system capabilities and desktop interfaces to Model Context Protocol (MCP) clients and local tooling.

---

## Architecture Overview

Textile organizes system capabilities into modular plugins with priority-based layer dispatch and worker process isolation:

| Concept | Role | Description |
|---|---|---|
| **Loom** | Dispatch Engine | Resolves capability priority, routes tool calls, and manages subprocess isolation. |
| **Skein** | Plugin Registry | Discovers entrypoints, loads dynamic plugins, and manages lifecycle states. |
| **Yarn** | Capability Module | Base class grouping related system capabilities and protocol implementations. |
| **Strand** | Tool Definition | Callable function with Pydantic v2 argument validation and capability tiering. |
| **Weft** | Stream Interceptor | Real-time token pattern matcher for streaming conversational output. |
| **Warp** | Event Broker | Asynchronous pub/sub event distribution system for system state and UI events. |
| **Tapestry** | State Store | In-memory key-value ledger for active context, notices, and session state. |
| **Twill** | MCP Server | Standard Model Context Protocol (stdio) interface for AI assistants. |
| **Seams** | Health Diagnostics | Dependency resolution, conflict detection, and diagnostic audit engine. |
| **Weave** | Voice Client | Embedded voice companion implemented as an MCP client powered by LiveKit and Gemini. |

---

## Prerequisites

To run Textile with conversational voice companion (**Weave**) and desktop presence (**Canvas**):

1. **Google Gemini API Key** (required for Weave voice agent):
   ```bash
   export GOOGLE_API_KEY="your-gemini-api-key"
   ```

2. **LiveKit CLI (`lk`)** (required for Weave interactive console and dev modes):
   ```bash
   curl -sSL https://get.livekit.io/cli | bash
   lk cloud auth
   ```

3. **Quickshell** (Highly Recommended, for the desktop Canvas Face UI):
   ```bash
   # Arch Linux / AUR
   paru -S quickshell-git
   ```

---

## CLI Reference

```bash
# Manage yarn registry and lifecycle
uv run textile skein
uv run textile skein disable <yarn_name>
uv run textile skein enable <yarn_name>

# Inspect active strands, parameter schemas, and layer priority
uv run textile loom
uv run textile loom --yarn <yarn_name>

# Run dependency audit and system health checks
uv run textile seams

# View priority layer hierarchy (Layer 150 to Layer 10)
uv run textile layers

# Execute a strand directly
uv run textile call clipboard_set text="Hello from Textile"
uv run textile call clipboard_get

# Control Canvas UI state
uv run textile canvas launch
uv run textile canvas mood thinking
uv run textile canvas talk on
uv run textile canvas close

# Start the Twill MCP server over stdio
uv run textile twill

# Launch the embedded Weave voice companion
uv run textile weave
```

---

## Authoring Yarns

Custom capability modules subclass `BaseYarn`. Functions decorated with `@strand` are automatically registered on the Loom and exposed over MCP:

```python
from typing import Optional
from textile.core.base import BaseYarn, CapabilityTier, strand, LAYER_DESKTOP_PROTOCOL

class CustomMediaYarn(BaseYarn):
    publisher = "community"
    name = "media_control"
    version = "1.0.0"
    layer = LAYER_DESKTOP_PROTOCOL  # Layer 50

    # Optional: declare isolated runtime dependencies
    python_dependencies = ["mpris2>=1.0.2"]

    @strand(description="Toggle playback state.", tier=CapabilityTier.INTERACT)
    def toggle_playback(self, player: Optional[str] = None) -> str:
        """Toggle media playback.

        :param player: Optional player identifier.
        """
        return f"Toggled playback on {player or 'default'}"

    @strand(description="Set volume percentage.", tier=CapabilityTier.INTERACT)
    def set_volume(self, level: int) -> str:
        """Set volume percentage.

        :param level: Volume level between 0 and 100.
        """
        return f"Volume set to {level}%"
```

Pydantic v2 validates inputs, coerces types, and generates JSON Schema specifications for MCP clients.

---

## Security and Capability Tiers

Textile enforces origin-blind execution tiers to maintain system integrity:

- **Capability Tiers**: Strands are assigned operational tiers (`OBSERVE`, `INTERACT`, `MUTATE`, `PRIVILEGED`, `SYSTEM_EXEC`). Elevated operations are automatically isolated in dedicated subprocesses.
- **Privilege Delegation**: Elevated operations interface with system authorization managers and message buses using predefined policy rules.
- **Accessibility & Protocol Automation**: Non-intrusive semantic interaction with desktop application trees, window managers, and clipboard buffers.
- **POSIX & Kernel Interfaces**: Safe filesystem transactions, inotify directory monitors, hardware telemetry, and process management.

---

## Canvas Desktop Presence

Textile Canvas is an optional desktop overlay rendered via QtQuick and Quickshell:

- **17 Preset Mood States**: `neutral`, `happy`, `excited`, `celebrating`, `thinking`, `focused`, `listening`, `curious`, `calm`, `shy`, `mischievous`, `confused`, `surprised`, `alert`, `sleepy`, `error`, `glitch`.
- **Stream Interception**: Semantic tokens (`<mood:...>`, `<gaze:x,y>`) are parsed from streaming text in real time to update UI state.
- **Decoupled Architecture**: Operates as a separate process communicating via IPC, with full CLI control.

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




