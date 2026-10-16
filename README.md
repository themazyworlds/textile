# Textile

[![CI](https://github.com/themazyworlds/textile/actions/workflows/ci.yml/badge.svg)](https://github.com/themazyworlds/textile/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/themazyworlds/textile.svg)](LICENSE)
[![Python 3.15+](https://img.shields.io/badge/python-3.15%2B-blue.svg)](https://www.python.org/downloads/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: Pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)

Layered Linux automation runtime, security supervisor, and Model Context Protocol (MCP) server for desktop intelligence.

---

## Architecture

- **Twill (MCP Server)**: Exposes active capability strands over Model Context Protocol (stdio) to external assistants, clients, and IDEs.
- **Loom & Skein (Orchestration Engine)**: Compiles and dispatches capability strands across a prioritized layer hierarchy (0 to 1000). Higher numeric layers deterministically override lower layers.
- **Elastic (Event Fabric)**: Low-latency cross-process event bus featuring urgency-based filtering (`AMBIENT`, `NOTICE`, `ALERT`, `FLASH`), retained slot state storage, and SQLite WAL IPC synchronization.
- **Sensory Tapestry**: System blackboard recording real-time ambient status, process metadata, and tool execution history.
- **Bubblewrap Sandboxing**: Kernel namespace isolation for strand execution, enforcing read-only mounts, network restrictions, and workspace confinement.
- **TOTP 2FA Verification**: RFC 6238 time-based one-time password gate protecting `MUTATE`, `PRIVILEGED`, and `SYSTEM_EXEC` execution tiers against unauthorized or accidental mutation.

---

## Prerequisites

- **Python 3.15+** and [**uv**](https://github.com/astral-sh/uv)
- **Bubblewrap (`bwrap`)** (Required for sandboxed strand execution):

```bash
# Arch Linux
sudo pacman -S bubblewrap

# Debian / Ubuntu
sudo apt install bubblewrap

# Fedora
sudo dnf install bubblewrap
```

---

## Quick Start

### 1. Run the MCP Server (stdio)

Run the Model Context Protocol stdio interface for external clients:

```bash
uv run textile twill
```

### 2. Manage 2FA Authenticator (RFC 6238 TOTP)

Generate setup secrets and current authentication codes:

```bash
# Display 2FA setup URI and QR information
uv run textile 2fa

# Print current 6-digit verification code
uv run textile 2fa -c
```

### 3. CLI Execution and Inspection

```bash
# List all registered strands
uv run textile strands

# Filter strands by capability tier
uv run textile strands --tier observe

# Inspect parameter schema and documentation for a strand
uv run textile inspect hyprland_focus_workspace

# Execute a strand directly
uv run textile call clipboard_set text="Textile ready"
uv run textile call clipboard_get

# Execute a privileged strand using 2FA
uv run textile call hyprland_exit_session --otp auto
```

### 4. Runtime and Yarn Inspection

```bash
# Inspect layer hierarchy, active yarns, and capability overrides
uv run textile skein

# List discovered yarn packages and search paths
uv run textile yarns

# View engine task ledger and blackboard status
uv run textile tapestry
```

### 5. User Settings Configuration

Per-yarn user configurations are managed in `~/.config/textile/settings.toml`:

```bash
# Generate documented configuration template
uv run textile settings init

# View settings schema for a specific yarn
uv run textile settings docs hyprland
```

---

## Capability Tiers and Security Policy

Every strand declares an explicit capability tier governing execution privileges:

| Tier | Policy Gate | Sandboxing Profile | Typical Operations |
| :--- | :--- | :--- | :--- |
| `OBSERVE` | Open (No 2FA) | Read-only mounts | Telemetry queries, sensor reads, window state |
| `INTERACT` | Open (No 2FA) | Workspace / Network mounts | Desktop notifications, window focus, clipboard |
| `MUTATE` | 2FA Required | Isolated write mounts | Persistent file modifications, config updates |
| `PRIVILEGED` | 2FA Required | Host execution boundary | Session exit, power management, system reboots |
| `SYSTEM_EXEC` | 2FA Required | Full host access | Package management, kernel modules, system-level execution |

---

## Discovery Search Paths

Yarns are discovered dynamically using ordered XDG-compliant search locations:

1. `TEXTILE_YARN_PATH` environment variable override (colon-delimited)
2. User configuration directory: `~/.config/textile/yarns/`
3. User installed data directory: `~/.local/share/textile/yarns/`
4. System-wide installed directories: `/usr/local/share/textile/yarns/`, `/usr/share/textile/yarns/`

---

## Authoring Capability Yarns

To author new capability packages, use the standalone SDK: [**Needle**](https://github.com/themazyworlds/textile-needle).

```bash
uv add needle
```

See the [Needle documentation](https://github.com/themazyworlds/textile-needle) for `@strand` and `Yarn` contracts.
