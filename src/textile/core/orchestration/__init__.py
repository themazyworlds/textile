"""
Textile Orchestration Functional Domain Package.
Provides runtime dispatching (Loom), intent compilation & discovery (Skein),
prompt instructions (FabricInstructions), core fabric (Fabric), and MCP protocol server (Twill).
"""

from textile.core.orchestration.fabric import core_fabric_yarn
lazy from textile.core.orchestration.instructions import FabricInstructions, fabric_instructions
lazy from textile.core.orchestration.loom import Loom, loom
lazy from textile.core.orchestration.skein import Skein, skein
lazy from textile.core.orchestration.twill import create_twill_server, run_twill

__all__ = [
    "FabricInstructions",
    "Loom",
    "Skein",
    "core_fabric_yarn",
    "create_twill_server",
    "fabric_instructions",
    "loom",
    "run_twill",
    "skein",
]
