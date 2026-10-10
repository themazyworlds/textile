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

- **Model Context Protocol (`Twill`)**: Exposes desktop tools and system controls to Claude, Cursor, Antigravity, and any MCP client over stdio.
- **Autonomous Voice Companion (`Weave`)**: Full-duplex conversational voice interface using LiveKit and Gemini Realtime with streaming semantic attunements.
- **Event & Sensory Fabric (`Elastic`)**: Unified cross-process event bus with urgency tiers, retained slot management, and SQLite WAL IPC synchronization.
- **Capability Yarns (`@strand` & `@weft`)**: Decorate Python methods with `@strand` for tools and `@weft` for real-time streaming token interception with Pydantic v2 validation.
- **Directory-Isolated Packaging**: Every capability yarn is a self-contained directory governed by standard `pyproject.toml` metadata and dedicated virtual environments.
- **Layered Dispatch (`Loom` & `Skein`)**: Prioritized layer hierarchy (0 to 1000) allowing specialized compositors, session managers, and user overrides to override lower OS fallbacks cleanly.
- **Bubblewrap Sandboxing**: Hardware-enforced process isolation and fail-closed kernel namespaces (filesystem read-only bind mounts, isolated `/tmp` and `/home`, network stack filtering, PID/IPC unsharing).
- **RFC 6238 TOTP 2FA Security**: Multi-tier capability enforcement (`OBSERVE`, `INTERACT`, `MUTATE`, `PRIVILEGED`) backed by standard 6-digit TOTP authentication with single-use timestep replay protection and non-blocking desktop notifications.
- **Canvas UI**: Quickshell Wayland overlay for dynamic emotive expressions, mood animations, and visual desktop presence.

---

## Prerequisites

- **Python 3.14+** and [**`uv`**](https://github.com/astral-sh/uv)

- **Bubblewrap (`bwrap`)** (Required for sandboxed strand execution):
  ```bash
  # Arch Linux
  sudo pacman -S bubblewrap

  # Debian / Ubuntu
  sudo apt install bubblewrap

  # Fedora
  sudo dnf install bubblewrap
  ```

- **Google Gemini API Key** (Required for Weave voice agent):
  ```bash
  export GOOGLE_API_KEY="your-gemini-api-key"
  ```

- **LiveKit CLI (`lk`)** (Required for Weave voice dev and console streaming):
  ```bash
  # Arch Linux
  yay -S livekit-cli

  # Debian / Ubuntu / Fedora / Generic Linux
  curl -sSL https://get.livekit.io/cli | bash
  ```

- **Quickshell** (Optional, for the desktop Canvas UI):
  ```bash
  # Arch Linux
  yay -S quickshell

  # Fedora
  sudo dnf copr enable outfoxxed/quickshell && sudo dnf install quickshell
  ```

---

## Quick Start

### 1. Run the MCP Server (stdio)
Connect external AI coding assistants and agents directly to your Linux desktop:
```bash
uv run textile twill
```

### 2. Configure 2FA (RFC 6238 TOTP)
Textile protects `PRIVILEGED` and `MUTATE` operations with TOTP 2FA:
```bash
# View authenticator setup URI (for Google Authenticator, Aegis, 1Password, Bitwarden)
uv run textile 2fa

# Generate current 6-digit TOTP code directly from the CLI
uv run textile 2fa -c
```

### 3. Direct CLI Execution & Inspection
```bash
# List all registered strands across all active yarns
uv run textile strands

# Filter strands by capability tier (observe, interact, mutate, privileged)
uv run textile strands --tier observe

# Inspect parameter schema and documentation for a strand
uv run textile inspect hyprland_get_windows

# Execute a strand directly
uv run textile call clipboard_set text="Hello from Textile"
uv run textile call clipboard_get

# Execute a privileged strand with 2FA confirmation
uv run textile call hyprland_exit_session --otp auto
```

### 4. Skein, Yarns & Tapestry State Inspection
```bash
# Inspect active yarns, layer resolution, and capability overrides
uv run textile skein

# List all discovered capability yarns and paths
uv run textile yarns

# View engine task ledger and sensory blackboard state
uv run textile tapestry
```

---

## Capability Tiers & Security Policy

Every strand declares an explicit capability tier governing execution and authorization:

| Tier | Policy Gate | Sandboxing | Description |
| :--- | :--- | :--- | :--- |
| `OBSERVE` | Open (No 2FA) | Read-only mounts | Read-only sensory telemetry, window lists, system status |
| `INTERACT` | Open (No 2FA) | Workspace / Network binds | Safe user interactions, setting clipboard, launching apps |
| `MUTATE` | 2FA Confirmation | Workspace write binds | Modifying persistent state, files, or configs |
| `PRIVILEGED` | 2FA Confirmation | Host execution / Root gate | Session termination, reboot, power management, kernel control |

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
from textile import Yarn, strand
from textile.core.execution.strands import CapabilityTier


class MediaControlYarn(Yarn):
    @strand(tier=CapabilityTier.INTERACT)
    async def media_play_pause(self, target: str | None = None) -> str:
        """Play or pause media playback."""
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
model = "gemini-2.5-flash"
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
