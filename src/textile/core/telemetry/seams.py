"""
Textile Seams - Integrity Diagnostics, Dependency Probing, and Circuit Breaker Facade.
Delegates low-level dependency checks to probes.py and auditing to auditor.py.
"""

from typing import Any

from textile.core.telemetry.auditor import (
    AuditSummary,
    HealthStatus,
    StrandIntegrityReport,
    SystemAuditReport,
    YarnIntegrityReport,
    audit_all,
    audit_strand,
    audit_yarn,
)
from textile.core.telemetry.log import get_logger
from textile.core.telemetry.probes import (
    DependencyCheck,
    DependencyType,
    check_binary,
    check_device_node,
    check_env_variable,
    check_python_dependency,
    check_python_module,
    check_socket,
    evaluate_dependencies,
)

logger = get_logger(__name__)

__all__ = [
    "AuditSummary",
    "DependencyCheck",
    "DependencyType",
    "HealthStatus",
    "SeamOrchestrator",
    "StrandIntegrityReport",
    "SystemAuditReport",
    "YarnIntegrityReport",
    "seams",
]


class SeamOrchestrator:
    """Orchestrator facade monitoring yarn health, system dependencies, and runtime contract compliance."""

    def __init__(self, loom_instance: Any | None = None, skein_instance: Any | None = None):
        self._loom = loom_instance
        self._skein = skein_instance
        self._failure_counts: dict[str, int] = {}
        self._max_consecutive_failures = 3

    def set_loom(self, loom_instance: Any) -> None:
        self._loom = loom_instance

    def set_skein(self, skein_instance: Any) -> None:
        self._skein = skein_instance

    def check_binary(self, binary_name: str, optional: bool = False) -> DependencyCheck:
        return check_binary(binary_name, optional)

    def check_device_node(
        self, device_path: str, write_access: bool = False, optional: bool = False
    ) -> DependencyCheck:
        return check_device_node(device_path, write_access=write_access, optional=optional)

    def check_socket(self, socket_path: str, optional: bool = False) -> DependencyCheck:
        return check_socket(socket_path, optional)

    def check_python_module(self, module_name: str, optional: bool = False) -> DependencyCheck:
        return check_python_module(module_name, optional)

    def check_python_dependency(self, req: str, optional: bool = False) -> DependencyCheck:
        return check_python_dependency(req, optional)

    def check_env_variable(self, var_name: str, optional: bool = False) -> DependencyCheck:
        return check_env_variable(var_name, optional)

    def evaluate_dependencies(self, yarn: Any) -> list[DependencyCheck]:
        return evaluate_dependencies(yarn)

    def audit_strand(self, strand: Any, yarn: Any, loom_inst: Any | None = None) -> StrandIntegrityReport:
        l_inst = self._resolve_loom(loom_inst)
        return audit_strand(strand, yarn, l_inst)

    def _resolve_loom(self, loom_inst: Any = None) -> Any:
        if loom_inst is not None:
            return loom_inst
        if self._loom is not None:
            return self._loom
        raise RuntimeError("Loom instance not configured for SeamOrchestrator")

    def _resolve_skein(self, skein_inst: Any = None) -> Any:
        if skein_inst is not None:
            return skein_inst
        if self._skein is not None:
            return self._skein
        raise RuntimeError("Skein instance not configured for SeamOrchestrator")

    def audit_yarn(self, yarn: Any, skein_inst: Any = None, loom_inst: Any = None) -> YarnIntegrityReport:
        s_inst = self._resolve_skein(skein_inst)
        l_inst = self._resolve_loom(loom_inst)
        return audit_yarn(yarn, s_inst, l_inst)

    def audit_all(self, loom_inst: Any | None = None, skein_inst: Any | None = None) -> dict[str, Any]:
        s_inst = self._resolve_skein(skein_inst)
        l_inst = self._resolve_loom(loom_inst)
        report = audit_all(l_inst, s_inst)
        return report.model_dump()

    def record_strand_execution(self, strand_name: str, success: bool, error: str | None = None) -> None:
        """Record strand execution success or failure for circuit breaker monitoring."""
        if success:
            self._failure_counts[strand_name] = 0
            return

        cnt = self._failure_counts.get(strand_name, 0) + 1
        self._failure_counts[strand_name] = cnt
        logger.warning(
            "seams.strand_failed",
            strand=strand_name,
            failures=cnt,
            max_failures=self._max_consecutive_failures,
            error=error,
        )

        if cnt >= self._max_consecutive_failures:
            logger.error(
                "seams.circuit_breaker_tripped",
                strand=strand_name,
                failures=cnt,
                max_failures=self._max_consecutive_failures,
            )


seams = SeamOrchestrator()
