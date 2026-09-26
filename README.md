# Textile

[![CI](https://github.com/themazyworlds/textile/actions/workflows/ci.yml/badge.svg)](https://github.com/themazyworlds/textile/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/themazyworlds/textile.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: Pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)
[![Last Commit](https://img.shields.io/github/last-commit/themazyworlds/textile.svg)](https://github.com/themazyworlds/textile/commits/main)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/themazyworlds/textile/pulls)

https://github.com/user-attachments/assets/291ad11e-f4ad-48ff-933b-03c0285b8933

A layered Linux engine for realtime voice companions, MCP tools, and desktop automation.

---

## Features

- **MCP Server (`Twill`)**: Exposes desktop tools and system controls to Claude, Cursor, and other MCP clients over stdio.
- **Voice Companion (`Weave`)**: Hands-free voice interface using LiveKit and Gemini Realtime for low-latency audio interaction.
- **Subprocess Isolation**: Dangerous system calls (`MUTATE`, `SYSTEM_EXEC`) run in isolated worker subprocesses to protect the main runtime.
- **Plugin System (`Yarns` & `@strand`)**: Decorate Python functions with `@strand` to generate Pydantic schemas and register tools automatically.
- **Layered Dispatch**: Override default tools across layers (10 to 150) to customize system behavior without editing core code.
- **Canvas UI**: Optional GTK / Wayland overlay for visual feedback, facial expressions, and agent status.

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

## Authoring Plugins (`Yarns` & `@strand`)

Subclass `Yarn` alongside a declarative static `.toml` manifest to create modular capability plugins. Functions decorated with `@strand` are automatically validated by Pydantic v2 and registered across the runtime and MCP:

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
from textile import Yarn, strand

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

## License

Textile is open-source software licensed under the [Apache License 2.0](LICENSE).
