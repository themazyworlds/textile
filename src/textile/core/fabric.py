"""
Textile Core Fabric - Built-in Native Core Strands & Engine Administration.
Provides baseline system inspection, task ledger management, integrity auditing, and test execution.
Layer 0 (Core Fabric).
"""

import logging
import os
import subprocess
import sys
from typing import Any

from textile import CapabilityTier, Yarn, YarnManifest, strand
from textile.core.elastic import elastic
from textile.core.seams import seams
from textile.core.tapestry import core_tapestry

logger = logging.getLogger(__name__)


class CoreFabricYarn(Yarn):
    """Native Core Fabric Administration & Health Diagnostics."""

    def __init__(self):
        manifest = YarnManifest(
            name="core",
            publisher="textile",
            version="1.0.0",
            layer=0,
            description="Textile Core runtime engine diagnostics and state inspection",
        )
        super().__init__(manifest=manifest)

    def is_available(self) -> bool:
        return True

    @strand(tier=CapabilityTier.OBSERVE)
    def textile_get_state(self) -> dict[str, Any]:
        """Get full snapshot of the sensory blackboard state slots and notices."""
        return elastic.get_state()

    @strand(tier=CapabilityTier.OBSERVE)
    def textile_get_sensory_state(self) -> dict[str, Any]:
        """Get the open sensory blackboard snapshot (sensory state slots and recent stitched notices/alerts)."""
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

    @strand(tier=CapabilityTier.OBSERVE)
    def audit_yarn_integrity(self) -> dict[str, Any]:
        """Audit system-wide yarn health, runtime dependencies, layer overrides, and schemas."""
        return seams.audit_all()

    @strand(tier=CapabilityTier.PRIVILEGED)
    def run_system_tests(self) -> str:
        """Run the full Textile system diagnostic unit, integration, and E2E test suite."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        test_script = os.path.join(project_root, "tests", "run_all_tests.py")
        if not os.path.exists(test_script):
            return "Error: test script tests/run_all_tests.py not found."

        try:
            res = subprocess.run(
                [sys.executable, test_script],
                cwd=project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
                check=False,
            )
            return res.stdout
        except (OSError, subprocess.SubprocessError) as e:
            return f"Error executing system test suite: {e}"


core_fabric_yarn = CoreFabricYarn()
