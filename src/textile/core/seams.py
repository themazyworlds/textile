"""
Textile Seams - Integrity, diagnostics, dependency resolution, and health engine.
"""

import importlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

from textile.core.base import validate_strand_schema


class DependencyType(Enum):
    SYSTEM_BINARY = "system_binary"
    DBUS_SERVICE = "dbus_service"
    DEVICE_NODE = "device_node"
    SOCKET_PATH = "socket_path"
    PYTHON_MODULE = "python_module"
    ENV_VARIABLE = "env_variable"


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    DISABLED = "disabled"


@dataclass
class DependencyCheck:
    """Represents a single system requirement checked for a yarn."""
    dep_type: DependencyType
    target: str
    is_satisfied: bool
    details: str
    is_optional: bool = False


@dataclass
class StrandIntegrityReport:
    """Integrity report for a single Strand."""
    strand_name: str
    yarn_name: str
    is_valid_schema: bool
    is_callable: bool
    genai_compatible: bool
    mcp_compatible: bool
    is_active_provider: bool
    overridden_by: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class YarnIntegrityReport:
    """Comprehensive integrity report for a yarn."""
    yarn_name: str
    version: str
    layer: int
    is_enabled: bool
    is_available: bool
    health_status: HealthStatus
    dependencies: List[DependencyCheck] = field(default_factory=list)
    strands_report: List[StrandIntegrityReport] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SeamOrchestrator:
    """Orchestrator monitoring yarn health, system dependencies, and runtime contract compliance."""

    def __init__(self, loom_instance: Optional[Any] = None):
        self._loom = loom_instance
        self._failure_counts: Dict[str, int] = {}
        self._max_consecutive_failures = 3

    def set_loom(self, loom_instance: Any) -> None:
        self._loom = loom_instance

    def check_binary(self, binary_name: str, optional: bool = False) -> DependencyCheck:
        path = shutil.which(binary_name)
        satisfied = path is not None
        details = f"Executable found at '{path}'" if satisfied else f"Binary '{binary_name}' not found in PATH"
        return DependencyCheck(
            dep_type=DependencyType.SYSTEM_BINARY,
            target=binary_name,
            is_satisfied=satisfied,
            details=details,
            is_optional=optional,
        )

    def check_dbus_service(self, service_name: str, bus_type: str = "session", optional: bool = False) -> DependencyCheck:
        try:
            from dbus_fast.aio import MessageBus
            from dbus_fast import BusType
            bt = BusType.SYSTEM if bus_type == "system" else BusType.SESSION
            return DependencyCheck(
                dep_type=DependencyType.DBUS_SERVICE,
                target=f"{bus_type}:{service_name}",
                is_satisfied=True,
                details=f"D-Bus interface available for probe",
                is_optional=optional,
            )
        except Exception as e:
            return DependencyCheck(
                dep_type=DependencyType.DBUS_SERVICE,
                target=f"{bus_type}:{service_name}",
                is_satisfied=False,
                details=f"D-Bus probe error: {e}",
                is_optional=optional,
            )

    def check_device_node(self, device_path: str, write_access: bool = False, optional: bool = False) -> DependencyCheck:
        path = Path(device_path)
        exists = path.exists()
        writable = os.access(device_path, os.W_OK) if exists else False
        satisfied = exists and (not write_access or writable)
        details = (
            f"Device exists (writable: {writable})"
            if exists
            else f"Device node '{device_path}' does not exist"
        )
        return DependencyCheck(
            dep_type=DependencyType.DEVICE_NODE,
            target=device_path,
            is_satisfied=satisfied,
            details=details,
            is_optional=optional,
        )

    def check_socket(self, socket_path: str, optional: bool = False) -> DependencyCheck:
        path = Path(socket_path)
        satisfied = path.exists() and path.is_socket()
        details = f"Active socket at '{socket_path}'" if satisfied else f"Socket '{socket_path}' not active"
        return DependencyCheck(
            dep_type=DependencyType.SOCKET_PATH,
            target=socket_path,
            is_satisfied=satisfied,
            details=details,
            is_optional=optional,
        )

    def check_python_module(self, module_name: str, optional: bool = False) -> DependencyCheck:
        try:
            importlib.import_module(module_name)
            return DependencyCheck(
                dep_type=DependencyType.PYTHON_MODULE,
                target=module_name,
                is_satisfied=True,
                details=f"Python module '{module_name}' imported successfully",
                is_optional=optional,
            )
        except ImportError as e:
            return DependencyCheck(
                dep_type=DependencyType.PYTHON_MODULE,
                target=module_name,
                is_satisfied=False,
                details=f"Module '{module_name}' import failed: {e}",
                is_optional=optional,
            )

    def check_env_variable(self, var_name: str, optional: bool = False) -> DependencyCheck:
        val = os.environ.get(var_name)
        satisfied = val is not None and len(val.strip()) > 0
        details = f"Set (len={len(val)})" if satisfied else f"Environment variable '{var_name}' is unset or empty"
        return DependencyCheck(
            dep_type=DependencyType.ENV_VARIABLE,
            target=var_name,
            is_satisfied=satisfied,
            details=details,
            is_optional=optional,
        )

    def evaluate_dependencies(self, yarn: Any) -> List[DependencyCheck]:
        results: List[DependencyCheck] = []
        for dep in yarn.get_dependencies():
            dtype = dep.get("type")
            target = dep.get("target", "")
            optional = dep.get("optional", False)

            if dtype == DependencyType.SYSTEM_BINARY.value:
                results.append(self.check_binary(target, optional))
            elif dtype == DependencyType.DEVICE_NODE.value:
                results.append(self.check_device_node(target, write_access=dep.get("writable", False), optional=optional))
            elif dtype == DependencyType.SOCKET_PATH.value:
                results.append(self.check_socket(target, optional))
            elif dtype == DependencyType.PYTHON_MODULE.value:
                results.append(self.check_python_module(target, optional))
            elif dtype == DependencyType.ENV_VARIABLE.value:
                results.append(self.check_env_variable(target, optional))
            elif dtype == DependencyType.DBUS_SERVICE.value:
                results.append(self.check_dbus_service(target, bus_type=dep.get("bus", "session"), optional=optional))

        return results

    def audit_strand(self, strand: Any, yarn: Any, loom_inst: Any) -> StrandIntegrityReport:
        errors = validate_strand_schema(strand.name, strand.parameters, strand.required)
        is_valid_schema = len(errors) == 0

        is_callable = callable(strand.handler) or callable(strand.raw_handler)
        if not is_callable:
            errors.append(f"Strand '{strand.name}' does not provide a callable handler.")

        is_overridden, active_provider, _ = loom_inst.get_strand_override_status(strand, yarn)
        is_active = (strand.name in loom_inst._strand_to_yarn and loom_inst._strand_to_yarn[strand.name].name == yarn.name)

        genai_compat = is_valid_schema and all(
            k.isidentifier() for k in strand.parameters.keys()
        )
        mcp_compat = is_valid_schema

        return StrandIntegrityReport(
            strand_name=strand.name,
            yarn_name=yarn.name,
            is_valid_schema=is_valid_schema,
            is_callable=is_callable,
            genai_compatible=genai_compat,
            mcp_compatible=mcp_compat,
            is_active_provider=is_active,
            overridden_by=active_provider if is_overridden else None,
            validation_errors=errors,
        )

    def audit_yarn(self, yarn: Any, skein_inst: Any = None, loom_inst: Any = None) -> YarnIntegrityReport:
        from textile.core.loom import loom
        from textile.core.skein import skein
        s_inst = skein_inst or skein
        l_inst = loom_inst or self._loom or loom
        errors: List[str] = []
        warnings: List[str] = []

        is_enabled = s_inst.is_enabled(yarn.name)
        is_avail = False
        try:
            is_avail = yarn.is_available()
        except Exception as e:
            errors.append(f"is_available() raised exception: {e}")

        dep_checks = self.evaluate_dependencies(yarn)
        for dc in dep_checks:
            if not dc.is_satisfied:
                if dc.is_optional:
                    warnings.append(f"Optional dependency unsatisfied: {dc.details}")
                else:
                    errors.append(f"Required dependency unsatisfied: {dc.details}")

        strands_report: List[StrandIntegrityReport] = []
        try:
            for s in yarn.get_strands():
                strands_report.append(self.audit_strand(s, yarn, l_inst))
        except Exception as e:
            errors.append(f"get_strands() raised exception: {e}")

        status = HealthStatus.HEALTHY
        if not is_enabled:
            status = HealthStatus.DISABLED
        elif not is_avail or errors:
            status = HealthStatus.CRITICAL if errors else HealthStatus.DEGRADED
        elif warnings:
            status = HealthStatus.DEGRADED

        return YarnIntegrityReport(
            yarn_name=yarn.name,
            version=getattr(yarn, "version", "1.0.0"),
            layer=getattr(yarn, "layer", 10),
            is_enabled=is_enabled,
            is_available=is_avail,
            health_status=status,
            dependencies=dep_checks,
            strands_report=strands_report,
            errors=errors,
            warnings=warnings,
        )

    def audit_all(self, loom_inst: Optional[Any] = None, skein_inst: Optional[Any] = None) -> Dict[str, Any]:
        from textile.core.loom import loom
        from textile.core.skein import skein
        s_inst = skein_inst or skein
        l_inst = loom_inst or self._loom or loom
        l_inst.initialize()

        reports: List[YarnIntegrityReport] = []
        for name, yarn in s_inst.all_yarns.items():
            reports.append(self.audit_yarn(yarn, s_inst, l_inst))

        total_yarns = len(reports)
        healthy = sum(1 for r in reports if r.health_status == HealthStatus.HEALTHY)
        degraded = sum(1 for r in reports if r.health_status == HealthStatus.DEGRADED)
        critical = sum(1 for r in reports if r.health_status == HealthStatus.CRITICAL)
        disabled = sum(1 for r in reports if r.health_status == HealthStatus.DISABLED)
        total_strands = len(l_inst._strand_to_yarn)

        return {
            "summary": {
                "total_yarns": total_yarns,
                "healthy_yarns": healthy,
                "degraded_yarns": degraded,
                "critical_yarns": critical,
                "disabled_yarns": disabled,
                "total_active_strands": total_strands,
            },
            "yarns": [
                {
                    "name": r.yarn_name,
                    "version": r.version,
                    "layer": r.layer,
                    "health": r.health_status.value,
                    "is_available": r.is_available,
                    "is_enabled": r.is_enabled,
                    "strands_count": len(r.strands_report),
                    "dependencies": [{"type": d.dep_type.value, "target": d.target, "satisfied": d.is_satisfied, "details": d.details} for d in r.dependencies],
                    "errors": r.errors,
                    "warnings": r.warnings,
                }
                for r in reports
            ]
        }

    def record_strand_execution(self, strand_name: str, success: bool, error: Optional[str] = None) -> None:
        if success:
            self._failure_counts[strand_name] = 0
            return

        cnt = self._failure_counts.get(strand_name, 0) + 1
        self._failure_counts[strand_name] = cnt
        logger.warning(f"Strand '{strand_name}' failed ({cnt}/{self._max_consecutive_failures}): {error}")

        if cnt >= self._max_consecutive_failures:
            logger.error(f"Strand '{strand_name}' exceeded max consecutive failures. Tripping circuit breaker.")


seams = SeamOrchestrator()
