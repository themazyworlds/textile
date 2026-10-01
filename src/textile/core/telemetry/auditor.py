"""
Textile System & Yarn Integrity Auditor Engine.
Compiles integrity reports for Yarns, Strands, and system-wide capability contracts.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from textile.core.execution.validation import validate_strand_schema
from textile.core.telemetry.probes import DependencyCheck, evaluate_dependencies


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    DISABLED = "disabled"


class StrandIntegrityReport(BaseModel):
    """Integrity report for a single Strand."""

    strand_name: str
    yarn_name: str
    is_valid_schema: bool
    is_callable: bool
    genai_compatible: bool
    mcp_compatible: bool
    is_active_provider: bool
    overridden_by: str | None = None
    validation_errors: list[str] = Field(default_factory=list)


class YarnIntegrityReport(BaseModel):
    """Comprehensive integrity report for a yarn."""

    yarn_name: str
    version: str = "1.0.0"
    layer: int = 10
    is_enabled: bool = True
    is_available: bool = True
    health_status: HealthStatus = HealthStatus.HEALTHY
    dependencies: list[DependencyCheck] = Field(default_factory=list)
    strands_report: list[StrandIntegrityReport] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditSummary(BaseModel):
    total_yarns: int = 0
    healthy_yarns: int = 0
    degraded_yarns: int = 0
    critical_yarns: int = 0
    disabled_yarns: int = 0
    total_active_strands: int = 0


class SystemAuditReport(BaseModel):
    summary: AuditSummary
    yarns: list[YarnIntegrityReport] = Field(default_factory=list)


def determine_yarn_health_status(
    is_enabled: bool,
    is_avail: bool,
    errors: list[str],
    warnings: list[str],
) -> HealthStatus:
    """Determine health status enum based on availability, errors, and warnings."""
    if not is_enabled:
        return HealthStatus.DISABLED
    if not is_avail or errors:
        return HealthStatus.CRITICAL if errors else HealthStatus.DEGRADED
    if warnings:
        return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY


def audit_strand(strand: Any, yarn: Any, loom_inst: Any) -> StrandIntegrityReport:
    """Audit schema compliance, handler callability, and capability override status for a Strand."""
    errors = validate_strand_schema(strand.name, strand.parameters, strand.required)
    is_valid_schema = len(errors) == 0

    is_callable = callable(strand.handler) or callable(strand.raw_handler)
    if not is_callable:
        errors.append(f"Strand '{strand.name}' does not provide a callable handler.")

    is_overridden, active_provider, _ = loom_inst.get_strand_override_status(strand, yarn)
    is_active = (
        strand.name in loom_inst._strand_to_yarn and loom_inst._strand_to_yarn[strand.name].name == yarn.name
    )

    genai_compat = is_valid_schema and all(k.isidentifier() for k in strand.parameters)
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


def audit_yarn(yarn: Any, skein_inst: Any, loom_inst: Any) -> YarnIntegrityReport:
    """Audit a single Yarn's dependencies, availability, health, and member Strands."""
    errors: list[str] = []
    warnings: list[str] = []

    is_enabled = skein_inst.is_enabled(yarn.name)
    is_avail = False
    try:
        is_avail = yarn.is_available()
    except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
        errors.append(f"is_available() raised exception: {e}")

    dep_checks = evaluate_dependencies(yarn)
    for dc in dep_checks:
        if not dc.is_satisfied:
            if dc.is_optional:
                warnings.append(f"Optional dependency unsatisfied: {dc.details}")
            else:
                errors.append(f"Required dependency unsatisfied: {dc.details}")

    strands_report: list[StrandIntegrityReport] = []
    try:
        for s in yarn.get_strands():
            strands_report.append(audit_strand(s, yarn, loom_inst))
    except (AttributeError, TypeError, ValueError, KeyError, OSError, RuntimeError) as e:
        errors.append(f"get_strands() raised exception: {e}")

    status = determine_yarn_health_status(is_enabled, is_avail, errors, warnings)

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


def audit_all(loom_inst: Any, skein_inst: Any) -> SystemAuditReport:
    """Perform a system-wide integrity and health audit of all registered Yarns and active Strands."""
    loom_inst.initialize()

    reports: list[YarnIntegrityReport] = [
        audit_yarn(yarn, skein_inst, loom_inst)
        for yarn in skein_inst.all_yarns.values()
    ]
    total_yarns = len(reports)
    healthy = sum(bool(r.health_status == HealthStatus.HEALTHY) for r in reports)
    degraded = sum(bool(r.health_status == HealthStatus.DEGRADED) for r in reports)
    critical = sum(bool(r.health_status == HealthStatus.CRITICAL) for r in reports)
    disabled = sum(bool(r.health_status == HealthStatus.DISABLED) for r in reports)
    total_strands = len(loom_inst._strand_to_yarn)

    return SystemAuditReport(
        summary=AuditSummary(
            total_yarns=total_yarns,
            healthy_yarns=healthy,
            degraded_yarns=degraded,
            critical_yarns=critical,
            disabled_yarns=disabled,
            total_active_strands=total_strands,
        ),
        yarns=reports,
    )
