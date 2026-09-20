"""
Basics Subsystem & Core Timing Feature Yarn for Textile.
Provides system timing delays, state inspection, and integrity checks.
Layer 10 (Core POSIX).
"""

from typing import Any

from textile.core.base import Yarn, strand
from textile.core.seams import seams
from textile.core.tapestry import core_tapestry, sensory_tapestry


class Basics(Yarn):
    """General System Timing & Integrity Basics Yarn."""

    def is_available(self) -> bool:
        return True

    @strand(description="Get the open sensory blackboard snapshot (sensory state slots and recent stitched notices/alerts).")
    def textile_get_sensory_state(self) -> dict[str, Any]:
        """Get the open sensory blackboard snapshot (sensory state slots and recent stitched notices/alerts)."""
        return sensory_tapestry.get_state()

    @strand(description="Get full snapshot of the sensory blackboard state slots and notices.")
    def textile_get_state(self) -> dict[str, Any]:
        """Get full snapshot of the sensory blackboard state slots and notices."""
        return sensory_tapestry.get_state()

    @strand(description="Get the core engine execution state (active running tasks and execution history).")
    def textile_get_engine_state(self) -> dict[str, Any]:
        """Get the core engine execution state (active running tasks and execution history)."""
        return core_tapestry.get_state()

    @strand(description="Cancel/terminate a currently running strand execution by its task ID or strand name.")
    def cancel_live_task(self, strand_name: str) -> str:
        """Cancel/terminate a currently running strand execution by its task ID or strand name.

        :param strand_name: The name or task ID of the running strand to cancel/terminate.
        """
        return core_tapestry.cancel_task(strand_name)

    @strand(description="Audit system-wide yarn health, runtime dependencies, layer overrides, and schemas.")
    def audit_yarn_integrity(self) -> dict[str, Any]:
        """Audit system-wide yarn health, runtime dependencies, layer overrides, and schemas."""
        return seams.audit_all()

    @strand(description="Run the full Textile system diagnostic unit, integration, and E2E test suite.")
    def run_system_tests(self) -> str:
        """Run the full Textile system diagnostic unit, integration, and E2E test suite."""
        import os
        import subprocess
        import sys

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
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
                timeout=60
            )
            return res.stdout
        except Exception as e:
            return f"Error executing system test suite: {e}"
