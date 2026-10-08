# Textile

[![CI](https://github.com/themazyworlds/textile/actions/workflows/ci.yml/badge.svg)](https://github.com/themazyworlds/textile/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/themazyworlds/textile.svg)](LICENSE)
[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: Pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)
[![Last Commit](https://img.shields.io/github/last-commit/themazyworlds/textile.svg)](https://github.com/themazyworlds/textile/commits/main)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/themazyworlds/textile/pulls)

https://github.com/user-attachments/assets/291ad11e-f4ad-48ff-933b-03c0285b8933

A sovereign, layered Linux automation fabric for real-time voice companions, MCP tools, and desktop intelligence.

---

## Features

- **Model Context Protocol (`Twill`)**: Exposes desktop tools and system controls to Claude, Cursor, and any MCP client over stdio.
- **Autonomous Voice Companion (`Weave`)**: Full-duplex conversational voice interface using LiveKit and Gemini Realtime with streaming semantic attunements.
- **Event & Sensory Fabric (`Elastic`)**: Unified cross-process event bus with urgency tiers, retained slot management, and SQLite WAL IPC synchronization.
- **Capability Yarns (`@strand` & `@weft`)**: Decorate Python methods with `@strand` for tools and `@weft` for real-time streaming token interception with Pydantic v2 validation.
- **Directory-Isolated Packaging**: Every capability yarn is a self-contained directory governed by standard `pyproject.toml` metadata and dedicated virtual environments.
- **Layered Dispatch (`Loom`)**: Prioritized layer hierarchy (0 to 1000) allowing specialized compositors, session managers, and user overrides to override lower OS fallbacks cleanly.
- **Subprocess & Visual OTP Security**: Single-use 4-digit Visual OTP confirmation for state-mutating and privileged operations.
- **Canvas UI**: Quickshell Wayland overlay for dynamic emotive expressions, mood animations, and visual presence.

---

## Prerequisites

- **Python 3.14+** and [**`uv`**](https://github.com/astral-sh/uv)

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
# List all active capability yarns and layer status
uv run textile skein
uv run textile yarns

# List and filter registered strands
uv run textile strands
uv run textile strands --tier observe

# Inspect detailed schema and documentation for a strand
uv run textile inspect hyprland_get_windows

# Inspect and document yarn settings schema
uv run textile settings docs weave

# Run automated dependency validation and health audit
uv run textile seams

# Execute any registered tool directly
uv run textile call clipboard_set text="Hello from Textile"
uv run textile call clipboard_get
```

---

## Authoring Capability Yarns

Each capability yarn is a self-contained directory containing a standard `pyproject.toml` and an entry point Python class inheriting from `textile.Yarn`:

### 1. `pyproject.toml`
```toml
[project]
name = "textile-yarn-media_control"
version = "1.0.0"
description = "Media player control integration"
authors = [{ name = "community" }]
requires-python = ">=3.14"
dependencies = [
    "mpris2>=1.0.2",
]

[tool.textile]
tailor = "community"
layer = 50                       # 0 (Core), 10 (POSIX), 50 (Protocol), 100 (Compositor), 150 (Session), 1000 (User)
resources = ["bin:playerctl", "socket:/run/user/1000/bus"]

[tool.textile.settings.default_player]
default = "spotify"
type = "str"
description = "Default media player client"
choices = ["spotify", "vlc", "firefox", "chromium"]
```

### 2. `media_control.py`
```python
from textile import Yarn, strand, weft
from textile.core.telemetry.elastic import EventUrgency, elastic


class MediaControlYarn(Yarn):
    @strand(description="Play or pause media playback", tier="interact")
    async def media_play_pause(self, target: str | None = None) -> str:
        player = target or self.settings.default_player
        # Implementation...
        return f"Toggled media play/pause on {player}"
```

---

## User Settings Configuration

User settings and overrides are stored in `~/.config/textile/settings.toml`:

```toml
# Textile settings
# Edit any setting below to customize per-yarn configuration.

[weave]
model = "gemini-3.8-live"
voice = "Puck"
instructions = "You are Textile Weave, an ultra-fast, friendly, intelligent voice companion embedded into Linux desktop."
```

To scaffold or view setting schemas:
```bash
# Generate settings template with descriptions and choices
uv run textile settings init

# View settings documentation for any yarn
uv run textile settings docs weave
```
