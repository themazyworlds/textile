# Textile

https://github.com/user-attachments/assets/291ad11e-f4ad-48ff-933b-03c0285b8933

A modular intelligence and automation framework for Linux. Textile provides a layered runtime dispatch engine and plugin architecture that exposes system capabilities and desktop interfaces to Model Context Protocol (MCP) clients, autonomous agents, and local tooling.

---

## Features

- **Layered Runtime Dispatch**: Priority-based layer hierarchy (Layer 10 to 150) supporting seamless capability overrides across system and desktop protocols.
- **Automated Subprocess Isolation**: Origin-blind execution tiers (`OBSERVE`, `INTERACT`, `MUTATE`, `PRIVILEGED`, `SYSTEM_EXEC`) that automatically isolate elevated operations in dedicated worker subprocesses.
- **Model Context Protocol (MCP)**: Native stdio MCP server (`Twill`) connecting external AI assistants (Claude, Cursor, Gemini, OpenCode).
- **Embedded Voice Companion**: Real-time full-duplex conversational voice agent (`Weave`) integrated with LiveKit and Google Gemini Live.
- **Type-Safe Plugin System**: Write capability modules (`Yarns`) using simple `@strand` decorators with automated Pydantic v2 schema generation.
- **Desktop Presence UI**: Optional Wayland desktop presence (`Canvas`) powered by Quickshell.

---

## Prerequisites

- **Python 3.12+** and [**`uv`**](https://github.com/astral-sh/uv)
- **Google Gemini API Key** (required for Weave voice agent):
  ```bash
  export GOOGLE_API_KEY="your-gemini-api-key"
  ```
- **LiveKit CLI (`lk`)** (required for Weave interactive console and dev modes):
  ```bash
  curl -sSL https://get.livekit.io/cli | bash
  lk cloud auth
  ```
- **Quickshell** (Highly Recommended, for the desktop Canvas UI):
  ```bash
  # Arch Linux / AUR
  paru -S quickshell-git
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

## Authoring Plugins (`Yarns` & `@strand`)

Subclass `Yarn` to create modular capability plugins. Functions decorated with `@strand` are automatically validated by Pydantic v2 and registered across the runtime and MCP:

```python
from typing import Optional
from textile.core.base import Yarn, CapabilityTier, strand, LAYER_DESKTOP_PROTOCOL

class CustomMediaYarn(Yarn):
    publisher = "community"
    name = "media_control"
    version = "1.0.0"
    layer = LAYER_DESKTOP_PROTOCOL  # Layer 50

    # Declare isolated runtime dependencies
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

---

## Architecture Overview

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

## Development & Testing

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





