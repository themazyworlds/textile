# Textile

[![CI](https://github.com/themazyworlds/textile/actions/workflows/ci.yml/badge.svg)](https://github.com/themazyworlds/textile/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/themazyworlds/textile.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: Pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)
[![Last Commit](https://img.shields.io/github/last-commit/themazyworlds/textile.svg)](https://github.com/themazyworlds/textile/commits/main)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/themazyworlds/textile/pulls)

https://github.com/user-attachments/assets/291ad11e-f4ad-48ff-933b-03c0285b8933

A sovereign, layered Linux automation fabric for real-time voice companions, MCP tools, and desktop intelligence.

---

## Features

- **Model Context Protocol (`Twill`)**: Exposes desktop tools and system controls to Claude, Cursor, and any MCP client over stdio.
- **Autonomous Voice Companion (`Weave`)**: Full-duplex conversational voice interface using LiveKit and Gemini Realtime with spontaneous cognition.
- **Event & Sensory Fabric (`Elastic`)**: Unified cross-process event bus with urgency tiers, retained slot management, and SQLite WAL IPC synchronization.
- **Cognition & Proactivity (`Shuttle`)**: Two-speed tension resonance (Flash vs. Curiosity drift) that allows Weave to speak spontaneously when system events occur.
- **Capability Plugins (`Yarns`, `@strand` & `@weft`)**: Decorate Python methods with `@strand` for tools and `@weft` for real-time streaming token interception with Pydantic v2 validation.
- **Layered Dispatch (`Loom`)**: Prioritized layer dispatch (10 to 150) allowing specialized compositors/session managers to override lower OS fallbacks cleanly.
- **Subprocess & Desk Isolation**: Sandboxed execution and reversible transaction undo stack for high-impact mutations.
- **Canvas UI**: Quickshell Wayland overlay for dynamic emotive expressions, mood animations, and visual presence.

---

## Prerequisites

- **Python 3.12+** and [**`uv`**](https://github.com/astral-sh/uv)

- **Google Gemini API Key** (required for Weave voice agent):
  ```bash
  export GOOGLE_API_KEY="your-gemini-api-key"
  ```

- **LiveKit CLI (`lk`)** (required for Weave interactive console and dev modes):
  ```bash
  # Arch Linux
  yay -S livekit-cli

  # NixOS
  nix-env -iA nixpkgs.livekit-cli

  # Debian / Ubuntu / Fedora / Generic Linux
  curl -sSL https://get.livekit.io/cli | bash
  ```

- **Quickshell** (Highly Recommended, for the desktop Canvas UI):
  ```bash
  # Arch Linux
  yay -S quickshell

  # Fedora
  sudo dnf copr enable outfoxxed/quickshell && sudo dnf install quickshell

  # NixOS
  nix-env -iA nixpkgs.quickshell

  # Debian / Ubuntu / Fedora / Generic Linux (Build from source)
  git clone https://github.com/quickshell-mirror/quickshell.git
  cd quickshell && cmake -B build && cmake --build build --target install
  ```

---

## Quick Start

### 1. Run the MCP Server (stdio)
Connect external AI coding assistants directly to your Linux desktop:
```bash
uv run textile twill
```

### 2. Launch the Voice Companion
Start the interactive conversational companion in your terminal:
```bash
uv run textile weave
```

### 3. Launch the Canvas UI
Start the reactive desktop presence:
```bash
uv run textile canvas launch
uv run textile canvas mood thinking
uv run textile canvas close
```

### 4. Direct CLI Execution & Inspection
```bash
# List all active capability modules and tools
uv run textile loom

# Run automated dependency validation and health audit
uv run textile seams

# Execute any registered tool directly
uv run textile call clipboard_set text="Hello from Textile"
uv run textile call clipboard_get
```

---

## Authoring Plugins (`Yarns`, `@strand` & `@weft`)

Subclass `Yarn` alongside a declarative static `.toml` manifest to create modular capability plugins. Functions decorated with `@strand` are automatically validated by Pydantic v2 and registered as callable tools; methods decorated with `@weft` intercept streaming speech tokens in real time:

### 1. `media_control.toml` (Manifest)
```toml
[yarn]
name = "media_control"           # Unique identifier for the capability yarn
publisher = "community"          # Author or organization
version = "1.0.0"                # Semantic version
manifest_version = 1
layer = 50                       # Priority layer: 10 (POSIX), 50 (Protocol), 100 (Compositor), 150 (Session Manager)
description = "Media player control integration"
resources = ["dbus-session"]     # Optional sandbox permissions: "display", "dbus-session", "dbus-system", "sound"

[dependencies]
python = ["mpris2>=1.0.2"]       # PyPI packages (installed in isolated execution)
system = ["playerctl"]           # System packages/binaries required on the host
```

### 2. `media_control.py` (Implementation)
```python
from textile import Yarn, strand, weft
from textile.core.elastic import EventUrgency, elastic

class CustomMediaYarn(Yarn):
    @strand(tier="interact")
    def toggle_playback(self, player: str | None = None) -> str:
        """Toggle media playback.

        :param player: Optional player identifier.
        """
        return f"Toggled playback on {player or 'default'}"

    @strand(tier="interact")
    def set_volume(self, level: int) -> str:
        """Set volume percentage.

        :param level: Volume level between 0 and 100.
        """
        elastic.occupy_seat("media.volume", level, source="media_control")
        return f"Volume set to {level}%"

    @weft(
        pattern=r"<volume:(?P<level>\d+)>",
        description="Stream attunement to set audio volume inline while speaking (e.g. <volume:80>)."
    )
    def on_stream_volume(self, level: int) -> None:
        """Real-time streaming token interceptor with automatic Pydantic coercion."""
        self.set_volume(level)
```

---

## Architecture Overview

| Concept | Role | Description |
|---|---|---|
| **Loom** | Dispatch Engine | Resolves capability priority, routes tool calls, and manages subprocess isolation. |
| **Skein** | Plugin Registry | Discovers entrypoints, loads dynamic plugins, and manages lifecycle states. |
| **Yarn** | Capability Module | Base class grouping related system capabilities and protocol implementations. |
| **Strand** | Tool Definition | Callable function with Pydantic v2 argument validation and capability tiering. |
| **Weft** | Stream Interceptor | Real-time token pattern matcher with Pydantic argument coercion for streaming conversational output. |
| **Elastic** | Event Fabric | Universal cross-process event bus and sensory blackboard with SQLite WAL sync and urgency tiers. |
| **Tapestry** | State Store | Persistent SQLite ledger for sensory notices, blackboard slots, and audit history. |
| **Shuttle** | Proactive Cognition | Spontaneous cognition engine managing tension decay, curiosity drift, and flash alerts. |
| **Twill** | MCP Server | Standard Model Context Protocol (stdio) interface for AI assistants. |
| **Seams** | Health Diagnostics | Pydantic-powered dependency resolution, conflict detection, and diagnostic audit engine. |
| **Weave** | Voice Companion | Full-duplex conversational agent powered by LiveKit and Gemini Realtime with automatic alert awakening. |

---

## License

Textile is open-source software licensed under the [Apache License 2.0](LICENSE).
