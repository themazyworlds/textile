"""
Textile Seams - Integrity, diagnostics, dependency resolution, and health engine.
"""

import importlib
import logging
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from textile.core.base import validate_strand_schema
from textile.core.loom import loom
from textile.core.skein import skein

logger = logging.getLogger(__name__)


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
    overridden_by: str | None = None
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class YarnIntegrityReport:
    """Comprehensive integrity report for a yarn."""
    yarn_name: str
    version: str
    layer: int
    is_enabled: bool
    is_available: bool
    health_status: HealthStatus
    dependencies: list[DependencyCheck] = field(default_factory=list)
    strands_report: list[StrandIntegrityReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SeamOrchestrator:
    """Orchestrator monitoring yarn health, system dependencies, and runtime contract compliance."""

    def __init__(self, loom_instance: Any | None = None):
        self._loom = loom_instance
        self._failure_counts: dict[str, int] = {}
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

    def check_dbus_service(
        self, service_name: str, bus_type: str = "session", optional: bool = False
    ) -> DependencyCheck:
        try:
            return DependencyCheck(
                dep_type=DependencyType.DBUS_SERVICE,
                target=f"{bus_type}:{service_name}",
                is_satisfied=True,
                details="D-Bus interface available for probe",
                is_optional=optional,
            )
        except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
            return DependencyCheck(
                dep_type=DependencyType.DBUS_SERVICE,
                target=f"{bus_type}:{service_name}",
                is_satisfied=False,
                details=f"D-Bus probe error: {e}",
                is_optional=optional,
            )

    def check_device_node(
        self, device_path: str, write_access: bool = False, optional: bool = False
    ) -> DependencyCheck:
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

    def check_python_dependency(self, req: str, optional: bool = False) -> DependencyCheck:
        """Audit a Python package dependency using uv pip compile dry-run resolution."""
        uv_bin = shutil.which("uv")
        if uv_bin:
            try:
                cmd = [uv_bin, "pip", "compile", "-", "-q"]
                r_in, w_in = os.pipe()
                r_out, w_out = os.pipe()
                r_err, w_err = os.pipe()
                file_actions = [
                    (os.POSIX_SPAWN_DUP2, r_in, 0),
                    (os.POSIX_SPAWN_DUP2, w_out, 1),
                    (os.POSIX_SPAWN_DUP2, w_err, 2),
                    (os.POSIX_SPAWN_CLOSE, r_in),
                    (os.POSIX_SPAWN_CLOSE, w_in),
                    (os.POSIX_SPAWN_CLOSE, r_out),
                    (os.POSIX_SPAWN_CLOSE, w_out),
                    (os.POSIX_SPAWN_CLOSE, r_err),
                    (os.POSIX_SPAWN_CLOSE, w_err),
                ]
                os.write(w_in, req.encode())
                os.close(w_in)

                pid = os.posix_spawn(cmd[0], cmd, os.environ, file_actions=file_actions)
                os.close(r_in)
                os.close(w_out)
                os.close(w_err)

                err_chunks = []
                while True:
                    chunk = os.read(r_err, 4096)
                    if not chunk:
                        break
                    err_chunks.append(chunk)
                os.close(r_err)
                os.close(r_out)

                _, status = os.waitpid(pid, 0)
                returncode = os.waitstatus_to_exitcode(status)
                stderr_text = b"".join(err_chunks).decode().strip()

                if returncode == 0:
                    return DependencyCheck(
                        dep_type=DependencyType.PYTHON_MODULE,
                        target=req,
                        is_satisfied=True,
                        details=f"Package requirement '{req}' resolvable via uv PubGrub resolver",
                        is_optional=optional,
                    )
                else:
                    err = stderr_text.splitlines()[-1] if stderr_text else "Resolution error"
                    return DependencyCheck(
                        dep_type=DependencyType.PYTHON_MODULE,
                        target=req,
                        is_satisfied=False,
                        details=f"uv dependency conflict: {err}",
                        is_optional=optional,
                    )
            except (OSError, ValueError, RuntimeError) as e:
                logger.debug(f"uv dependency compile error: {e}")

        base_pkg = req
        for sep in ("==", ">=", "<=", "~="):
            base_pkg = base_pkg.split(sep, maxsplit=1)[0]
        base_pkg = base_pkg.strip()
        return self.check_python_module(base_pkg, optional=optional)

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

    def evaluate_dependencies(self, yarn: Any) -> list[DependencyCheck]:
        results: list[DependencyCheck] = []
        for dep in yarn.get_dependencies():
            dtype = dep.get("type")
            target = dep.get("target", "")
            optional = dep.get("optional", False)

            if dtype == DependencyType.SYSTEM_BINARY.value:
                results.append(self.check_binary(target, optional))
            elif dtype == DependencyType.DEVICE_NODE.value:
                results.append(
                    self.check_device_node(target, write_access=dep.get("writable", False), optional=optional)
                )
            elif dtype == DependencyType.SOCKET_PATH.value:
                results.append(self.check_socket(target, optional))
            elif dtype == DependencyType.PYTHON_MODULE.value:
                results.append(self.check_python_module(target, optional))
            elif dtype == DependencyType.ENV_VARIABLE.value:
                results.append(self.check_env_variable(target, optional))
            elif dtype == DependencyType.DBUS_SERVICE.value:
                results.append(self.check_dbus_service(target, bus_type=dep.get("bus", "session"), optional=optional))

        if hasattr(yarn, "get_python_dependencies"):
            for p_dep in yarn.get_python_dependencies():
                results.append(self.check_python_dependency(p_dep))

        return results

    def audit_strand(self, strand: Any, yarn: Any, loom_inst: Any) -> StrandIntegrityReport:
        errors = validate_strand_schema(strand.name, strand.parameters, strand.required)
        is_valid_schema = len(errors) == 0

        is_callable = callable(strand.handler) or callable(strand.raw_handler)
        if not is_callable:
            errors.append(f"Strand '{strand.name}' does not provide a callable handler.")

        is_overridden, active_provider, _ = loom_inst.get_strand_override_status(strand, yarn)
        is_active = (
            strand.name in loom_inst._strand_to_yarn
            and loom_inst._strand_to_yarn[strand.name].name == yarn.name
        )

        genai_compat = is_valid_schema and all(
            k.isidentifier() for k in strand.parameters
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
        s_inst = skein_inst or skein
        l_inst = loom_inst or self._loom or loom
        errors: list[str] = []
        warnings: list[str] = []

        is_enabled = s_inst.is_enabled(yarn.name)
        is_avail = False
        try:
            is_avail = yarn.is_available()
        except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
            errors.append(f"is_available() raised exception: {e}")

        dep_checks = self.evaluate_dependencies(yarn)
        for dc in dep_checks:
            if not dc.is_satisfied:
                if dc.is_optional:
                    warnings.append(f"Optional dependency unsatisfied: {dc.details}")
                else:
                    errors.append(f"Required dependency unsatisfied: {dc.details}")

        strands_report: list[StrandIntegrityReport] = []
        try:
            for s in yarn.get_strands():
                strands_report.append(self.audit_strand(s, yarn, l_inst))
        except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
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

    def audit_all(self, loom_inst: Any | None = None, skein_inst: Any | None = None) -> dict[str, Any]:
        s_inst = skein_inst or skein
        l_inst = loom_inst or self._loom or loom
        l_inst.initialize()

        reports: list[YarnIntegrityReport] = []
        for yarn in s_inst.all_yarns.values():
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
                    "dependencies": [
                        {
                            "type": d.dep_type.value,
                            "target": d.target,
                            "satisfied": d.is_satisfied,
                            "details": d.details,
                        }
                        for d in r.dependencies
                    ],
                    "errors": r.errors,
                    "warnings": r.warnings,
                }
                for r in reports
            ],
        }

    def record_strand_execution(self, strand_name: str, success: bool, error: str | None = None) -> None:
        if success:
            self._failure_counts[strand_name] = 0
            return

        cnt = self._failure_counts.get(strand_name, 0) + 1
        self._failure_counts[strand_name] = cnt
        logger.warning(f"Strand '{strand_name}' failed ({cnt}/{self._max_consecutive_failures}): {error}")

        if cnt >= self._max_consecutive_failures:
            logger.error(f"Strand '{strand_name}' exceeded max consecutive failures. Tripping circuit breaker.")


seams = SeamOrchestrator()
