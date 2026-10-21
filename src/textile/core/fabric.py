"""
Textile Core Fabric - Native Core Strands & Engine Administration.
Provides baseline system inspection, task ledger management, and integrity auditing.
Layer 0 (Core Fabric).
"""

from typing import Any

from needle import Yarn, strand

lazy from textile.core.camshaft import camshaft


class CoreFabricYarn(Yarn):
    """Native Core Fabric Administration & Health Diagnostics."""

    def __init__(self) -> None:
        super().__init__(
            name="core",
            layer=0,
            description="Textile Core runtime engine diagnostics and state inspection",
            tailor="textile",
            version="1.0.0",
        )

    @strand.observe
    def textile_get_state(self) -> dict[str, Any]:
        """Get full snapshot of the sensory blackboard state slots and notices."""
        return camshaft.get_sensory_state()

    @strand.observe
    def textile_get_engine_state(self) -> dict[str, Any]:
        """Get the core engine execution state (active running tasks and execution history)."""
        return camshaft.get_engine_state()

    @strand.mutate
    def cancel_live_task(self, strand_name: str) -> str:
        """Cancel/terminate a currently running strand execution by its task ID or strand name.

        :param strand_name: The name or task ID of the running strand to cancel/terminate.
        """
        return camshaft.cancel_task(strand_name)


core_fabric_yarn = CoreFabricYarn()
camshaft.register_yarn(core_fabric_yarn)

__all__ = ["CoreFabricYarn", "core_fabric_yarn"]
