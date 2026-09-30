"""
Textile Orchestration Functional Domain Package.
Provides runtime dispatching (Loom), intent compilation & discovery (Skein),
stream attunements (StreamEngine), prompt instructions (FabricInstructions),
core fabric (Fabric), and MCP protocol server (Twill).
"""

from textile.core.orchestration.fabric import core_fabric_yarn
from textile.core.orchestration.instructions import FabricInstructions, fabric_instructions
from textile.core.orchestration.loom import Loom, loom
from textile.core.orchestration.skein import Skein, skein
from textile.core.orchestration.stream import StreamEngine, stream_engine
from textile.core.orchestration.twill import create_twill_server, run_twill

__all__ = [
    "FabricInstructions",
    "Loom",
    "Skein",
    "StreamEngine",
    "core_fabric_yarn",
    "create_twill_server",
    "fabric_instructions",
    "loom",
    "run_twill",
    "skein",
    "stream_engine",
]
