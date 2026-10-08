# Textile Agent Automation Reference Guide

This document is the reference guide for AI coding assistants and autonomous agents interacting with the Linux desktop and system subsystems via the Textile fabric.

---

## Core Architecture

Textile is a layered Linux automation fabric exposing desktop capabilities, system controls, and event fabrics over the Model Context Protocol (MCP).

### 1. Twill (MCP Server over Stdio)
Twill is the primary interface for external AI assistants (Claude, Cursor, Antigravity, etc.). It aggregates all active Strands into a standard Model Context Protocol server:
```bash
uv run textile twill
```

### 2. Loom (Runtime Dispatcher)
Loom handles in-memory strand execution, argument validation via Pydantic v2, and priority layer resolution (0 to 1000). Higher layers (e.g. specialized compositors or session managers) cleanly override lower OS fallbacks.

### 3. Skein (Capability Lifecycle & Registry)
Skein discovers and registers capability yarns from installed packages and custom user directories (`~/.config/textile/yarns/`). It handles settings persistence (`~/.config/textile/settings.toml`), dependency validation, and availability probes.

### 4. Elastic (Event & Sensory Fabric)
Elastic provides a real-time, cross-process event bus with priority urgency tiers, retained state slots, and SQLite WAL synchronization for desktop context sharing.

---

## Security Model & Capability Tiers

All tools (Strands) are categorized into explicit security tiers:

* **`OBSERVE`**: Read-only inspection (window lists, hardware sensors, system logs, active workspaces). Executes without user disruption.
* **`INTERACT`**: Non-destructive UI actions (focusing windows, switching workspaces, moving windows, setting timers).
* **`MUTATE` / `PRIVILEGED` / `SYSTEM_EXEC`**: State-altering and privileged operations (session finalization, root execution, process termination). May require a single-use 4-digit Visual OTP.

---

## Agent CLI Commands

Agents can query and inspect the fabric directly using the Textile CLI:

```bash
# Start MCP server over stdio
uv run textile twill

# List all discovered capability yarns and layer status
uv run textile skein
uv run textile yarns

# List all callable tools (strands)
uv run textile strands
uv run textile strands --tier observe

# Inspect parameter schema for a specific strand
uv run textile inspect <strand_name>

# Execute any strand directly with parameter validation
uv run textile call <strand_name> key=value

# Run automated health and dependency audits
uv run textile seams

# View documented settings and allowed options
uv run textile settings docs [yarn_name]
```
