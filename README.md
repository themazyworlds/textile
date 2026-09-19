# Textile: Linux Desktop Intelligence and Automation Fabric

<p align="center">
  <a href="https://github.com/themazyworlds/textile/actions/workflows/ci.yml"><img src="https://github.com/themazyworlds/textile/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
</p>

<p align="center">
  <video src="assets/canvas_showcase.mp4" width="720" controls autoplay loop muted playsinline style="border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5);"></video>
</p>

Textile is a high-performance, protocol-first desktop intelligence and automation subsystem for Linux. Powered by a decoupled microkernel architecture, it connects AI agents, full-duplex voice companions, and local CLI tools to the Linux desktop across all compositor, session, protocol, and kernel layers.

---

## System Architecture and Glossary

Textile is structured around a focused, decoupled weaving metaphor:

| Textile Concept | Engineering Equivalent | Purpose |
|---|---|---|
| **`Loom`** | Dispatch Engine & Executor | Manages runtime dispatch, capability overrides, and worker isolation. |
| **`Skein`** | Plugin Discovery & Registry | Discovers Yarns, PEP 621 entrypoints, and manages enable/disable state. |
| **`Yarn`** | Capability Module / Plugin | Domain capability class (e.g. `PackageKit`, `Polkit`, `Hyprland`). |
| **`Strand`** | Callable Tool / Function | Individual tool exposed to AI agents with Pydantic type validation. |
| **`Weft`** | Streaming Token Interceptor | Real-time regex pattern interceptor for conversational speech streams. |
| **`Warp`** | Universal Pub/Sub Event Bus | Low-latency asynchronous sensory and state event distribution. |
| **`Tapestry`** | Live State Blackboard | Dynamic sensory ledger tracking slots, active tasks, and notices. |
| **`Twill`** | MCP Server Interface | Model Context Protocol gateway connecting external AI assistants. |
| **`Seams`** | Diagnostics & Self-Healing | Automated dependency validation and PubGrub conflict resolver. |
| **`Weave`** | Voice AI Companion | Full-duplex live audio/vision agent powered by LiveKit and Gemini. |

---

## Prerequisites and Setup

To run Textile with full conversational voice companion (**Weave**) and emotive desktop avatar (**Canvas**) support:

1. **Google Gemini API Key** (for Gemini Live audio and multimodal model):
   ```bash
   export GOOGLE_API_KEY="your-gemini-api-key"
   ```

2. **LiveKit CLI (`lk`)** (for low-latency terminal audio and LiveKit Cloud integration):
   ```bash
   # Install lk CLI
   curl -sSL https://get.livekit.io/cli | bash

   # Authenticate with your LiveKit Cloud project
   lk cloud auth
   ```

3. **Quickshell** (for the 60 FPS emotive desktop avatar Face UI):
   ```bash
   # Arch Linux / AUR
   paru -S quickshell-git
   ```

---

## Quick Start and CLI Reference

```bash
# Manage yarn discovery, registry, publishers, and enable/disable states
uv run textile skein
uv run textile skein disable packagekit
uv run textile skein enable packagekit

# Inspect active strands, parameter schemas, and layer mappings on The Loom
uv run textile loom
uv run textile loom --yarn hyprland

# Run Seams diagnostics: yarn integrity, dependency audit, and OS health
uv run textile seams

# View priority layer hierarchy (Layer 150 -> Layer 10)
uv run textile layers

# Directly execute any strand from the terminal
uv run textile call clipboard_set text="Hello from Textile"
uv run textile call clipboard_get
uv run textile call hyprland_focus_workspace workspace="2"

# Control the Quickshell Canvas Face UI and dynamic mood engine
uv run textile canvas launch
uv run textile canvas mood excited
uv run textile canvas talk on
uv run textile canvas close

# Start the Twill Model Context Protocol (MCP) server (stdio)
uv run textile twill

# Launch the Weave real-time conversational desktop companion
uv run textile weave
```

---

## Authoring a Yarn (`@strand` and Pydantic v2)

Every capability module is a standard Python class subclassing `BaseYarn`. Writing a strand takes just **3 to 5 lines of Python code** with type annotations and docstrings:

```python
from typing import Literal, Optional
from textile.core.base import BaseYarn, CapabilityTier, strand, LAYER_DESKTOP_PROTOCOL

class CustomYarn(BaseYarn):
    publisher = "myname"
    name = "media_player"
    version = "1.0.0"
    layer = LAYER_DESKTOP_PROTOCOL  # Layer 50

    # Optional: declare external PyPI packages for automatic uv isolation
    python_dependencies = ["mpris2>=1.0.2"]

    @strand(description="Play or pause media playback.", tier=CapabilityTier.INTERACT)
    def toggle_playback(self, player: Optional[str] = None) -> str:
        """Play or pause media playback.

        :param player: Target player name (e.g., 'spotify').
        """
        return "Toggled playback"

    @strand(description="Adjust playback volume level.", tier=CapabilityTier.INTERACT)
    def set_volume(self, level: int) -> str:
        """Adjust playback volume level.

        :param level: Volume percentage (0 to 100).
        """
        return f"Volume set to {level}%"
```

Pydantic v2 automatically derives argument validation, type coercion, and MCP JSON Schemas directly from the signature and docstrings.

---

## Linux Desktop Subsystems and Privilege Control

Textile owns its privilege lifecycle cleanly through **Linux PolicyKit-1 (`polkit_*`) and D-Bus**:
- **System Pre-Authorization**: Pre-authorized elevated operations run instantly without UI dialogs.
- **AT-SPI Semantic Automation**: Coordinate-independent Linux GUI element querying, clicking, text insertion, and tab switching.
- **Compositor Control**: Direct socket IPC for Hyprland layout geometry, workspaces, night light, and focus.
- **POSIX and Kernel Telemetry**: Atomic filesystem operations, real-time inotify file monitoring, sensor telemetry, and hardware frequency queries.

---

## Textile Canvas: 60 FPS Emotive Desktop Avatar

Textile Canvas is a hardware-accelerated, real-time emotive desktop presence powered by [Quickshell](https://quickshell.outfoxxed.me/) and QtQuick. It gives voice AI companions and autonomous agents an expressive presence on the Linux desktop:

- **17 Mood Palettes**: `neutral`, `happy`, `excited`, `celebrating`, `thinking`, `focused`, `listening`, `curious`, `calm`, `shy`, `mischievous`, `confused`, `surprised`, `alert`, `sleepy`, `error`, `glitch`.
- **Zero-Latency Semantic Stream Attunement**: Weave and connected AI models emit inline semantic tags (e.g., `<mood:curious>`, `<gaze:8.0,-5.0>`) directly inside conversational streams.
- **Forehead Gem Ripple Mechanics**: Automatically pulses with water ripples whenever an autonomous agent initiates system automation or tool calls.
- **Organic Micro-Saccades and Physics**: Smooth 60 FPS mouth phoneme interpolation, biological eye micro-saccades, reactive head tilt inertia, and interactive elastic click bounce.
- **Self-Contained and Modular**: Packaged directly within the compositor yarn (`src/textile/yarns/compositor/canvas.qml`), auto-launching on startup with full CLI and IPC controls.

---

## Testing and Verification

```bash
# Run pytest test suite
uv run pytest

# Run end-to-end integration suite
uv run python tests/run_all_tests.py

# Build distribution wheel and source package
uv build
```

---

## License

Textile is open-source software licensed under the [Apache License 2.0](LICENSE).


