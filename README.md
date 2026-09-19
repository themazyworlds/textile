# Textile • Linux Desktop Intelligence & Automation Fabric

<p align="center">
  <img src="assets/canvas_showcase.gif" alt="Textile Canvas Emotive Desktop Avatar" width="720" style="border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.5);" />
</p>

Textile is a high-performance, protocol-first desktop intelligence and automation subsystem for Linux. Powered by a decoupled microkernel architecture, it seamlessly connects AI agents, full-duplex voice companions, and local CLI tools to the Linux desktop across all compositor, session, protocol, and kernel layers.

---

## 🏛️ System Architecture

Textile is structured around a focused, decoupled weaving metaphor:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Weave (Real-Time Voice & AI Engine)                  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Twill (MCP / Stdio JSON-RPC)
┌────────────────────────────────────▼────────────────────────────────────┐
│                       Loom (Runtime Dispatch Engine)                    │
│             High-speed in-memory strand execution & layer overrides     │
├─────────────────────────────────────────────────────────────────────────┤
│                       Skein (Yarn & Lifecycle Manager)                  │
│             Discovery, PEP 621 entrypoints, dependency auditing         │
└───────┬───────────────────┬─────────────────────┬───────────────────────┘
        │ Layer 150         │ Layer 100           │ Layer 50 / 10
        ▼                   ▼                     ▼
┌───────────────┐   ┌───────────────┐     ┌───────────────────────────────┐
│ Session Yarn  │   │  Compositor   │     │ Semantic Protocols & POSIX    │
│    (UWSM)     │   │  (Hyprland)   │     │ (AT-SPI, D-Bus, Polkit, Clipboard)│
└───────────────┘   └───────────────┘     └───────────────────────────────┘
```

1. **`Skein` (Discovery & Package Manager)**: Equivalent to `lazy.nvim`. Discovers built-in yarns, PEP 621 entrypoints (`[project.entry-points."textile.yarns"]`), and `~/.config/textile/yarns/`. Manages configuration persistence and health probes.
2. **`Loom` (High-Speed Runtime Dispatcher)**: Equivalent to `nvim-core`. Manages live in-memory strand execution, priority layer resolution (`150` ➔ `10`), and multi-process worker isolation (`_run_isolated`).
3. **`Twill` (Protocol Wire Gateway)**: Universal Model Context Protocol (MCP) server exposing all active strands to external AI assistants (Claude, Cursor, Antigravity, Weave).
4. **`Weave` (Voice AI Engine)**: Full-duplex conversational voice companion powered by LiveKit Agents and Google Gemini 2.0 / 3 Live Realtime APIs.
5. **`Yarns & Strands`**: Modular capability units written in clean Python with Pydantic v2 type hints and `@strand` reflection.

---

## 🚀 Quick Start & CLI Reference

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

# Control the Quickshell Canvas Face UI & dynamic mood engine
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

## 🛠️ Authoring a Yarn (`@strand` & Pydantic v2)

Every capability module is a standard Python class subclassing `BaseYarn`. Writing a strand takes just **3–5 lines of natural Python code** with pure type annotations and docstrings:

```python
from typing import Literal, Optional
from textile.core.base import BaseYarn, strand, LAYER_DESKTOP_PROTOCOL

class CustomYarn(BaseYarn):
    publisher = "myname"
    name = "media_player"
    version = "1.0.0"
    layer = LAYER_DESKTOP_PROTOCOL  # Layer 50

    @strand(description="Play or pause media playback.")
    def toggle_playback(self, player: Optional[str] = None) -> str:
        """Play or pause media playback.

        :param player: Target player name (e.g., 'spotify').
        """
        # Your logic here
        return "Toggled playback"

    @strand(description="Adjust playback volume level.")
    def set_volume(self, level: int) -> str:
        """Adjust playback volume level.

        :param level: Volume percentage (0 to 100).
        """
        return f"Volume set to {level}%"
```

Pydantic v2 automatically derives argument validation, type coercion, and MCP JSON Schemas directly from the signature and docstrings.

---

## 🛡️ Linux Desktop Subsystems & Privilege Control

Textile owns its privilege lifecycle cleanly through **Linux PolicyKit-1 (`polkit_*`) and D-Bus**:
- **System Pre-Authorization**: Pre-authorized elevated operations run instantly with zero UI dialogs.
- **AT-SPI Semantic Automation**: Coordinate-independent Linux GUI element querying, clicking, text insertion, and tab switching.
- **Compositor Control**: Direct socket IPC for Hyprland layout geometry, workspaces, night light, and focus.
- **POSIX & Kernel Telemetry**: Atomic filesystem operations, real-time inotify file monitoring, sensor telemetry, and hardware frequency queries.

---

## 🎨 Textile Canvas • 60 FPS Emotive Desktop Avatar

Textile Canvas is a hardware-accelerated, real-time emotive desktop presence powered by [Quickshell](https://quickshell.outfoxxed.me/) and QtQuick. It gives voice AI companions and autonomous agents a lively, organic face on the Linux desktop:

- **17 Rich Mood Palettes**: `neutral`, `happy`, `excited`, `celebrating`, `thinking`, `focused`, `listening`, `curious`, `calm`, `shy`, `mischievous`, `confused`, `surprised`, `alert`, `sleepy`, `error`, `glitch`.
- **Zero-Latency Semantic Stream Attunement**: Weave and connected AI models emit inline semantic tags (e.g., `<mood:curious>`, `<gaze:8.0,-5.0>`) directly inside conversational streams.
- **Harmonic Forehead Gem Ripple Mechanics**: Automatically pulses with harmonic water ripples whenever an autonomous agent initiates system automation or tool calls.
- **Organic Micro-Saccades & Physics**: Smooth 60 FPS mouth phoneme interpolation, biological eye micro-saccades, reactive head tilt inertia, and interactive elastic click bounce.
- **Self-Contained & Modular**: Packaged directly within the compositor yarn (`src/textile/yarns/compositor/canvas.qml`), auto-launching on startup with full CLI and IPC controls.

---

## 🧪 Testing & Verification

```bash
# Run pytest test suite
uv run pytest

# Run end-to-end integration suite
uv run python tests/run_all_tests.py

# Build distribution wheel and source package
uv build
```

---

## 📄 License

Textile is open-source software licensed under the [Apache License 2.0](LICENSE).

