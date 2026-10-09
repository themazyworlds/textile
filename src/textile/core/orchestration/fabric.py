"""
Textile Core Fabric - Native Core Strands & Engine Administration.
Provides baseline system inspection, task ledger management, and integrity auditing.
Layer 0 (Core Fabric).
"""

import logging
from typing import Any

from textile.core.execution.decorators import strand
from textile.core.execution.strands import CapabilityTier
from textile.core.execution.yarn import Yarn
from textile.core.orchestration.skein import skein
from textile.core.telemetry.elastic import elastic
from textile.core.telemetry.ledger import core_tapestry

logger = logging.getLogger(__name__)


class CoreFabricYarn(Yarn):
    """Native Core Fabric Administration & Health Diagnostics."""

    name = "core"
    tailor = "textile"
    version = "1.0.0"
    layer = 0
    description = "Textile Core runtime engine diagnostics and state inspection"

    def is_available(self) -> bool:
        return True

    @strand(tier=CapabilityTier.OBSERVE)
    def textile_get_state(self) -> dict[str, Any]:
        """Get full snapshot of the sensory blackboard state slots and notices."""
        return elastic.get_state()

    @strand(tier=CapabilityTier.OBSERVE)
    def textile_get_engine_state(self) -> dict[str, Any]:
        """Get the core engine execution state (active running tasks and execution history)."""
        return core_tapestry.get_state()

    @strand(tier=CapabilityTier.MUTATE)
    def cancel_live_task(self, strand_name: str) -> str:
        """Cancel/terminate a currently running strand execution by its task ID or strand name.

        :param strand_name: The name or task ID of the running strand to cancel/terminate.
        """
        return core_tapestry.cancel_task(strand_name)


core_fabric_yarn = CoreFabricYarn()
skein.register_yarn(core_fabric_yarn)
