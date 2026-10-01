"""
Textile System Probes & Dependency Evaluation Engine.
Provides low-level OS requirement checking for binaries, device nodes, sockets, python modules, and env vars.
"""

import importlib
import os
import shutil
import subprocess
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)


class DependencyType(StrEnum):
    SYSTEM_BINARY = "system_binary"
    DEVICE_NODE = "device_node"
    SOCKET_PATH = "socket_path"
    PYTHON_MODULE = "python_module"
    ENV_VARIABLE = "env_variable"


class DependencyCheck(BaseModel):
    """Represents a single system requirement checked for a yarn."""

    dep_type: DependencyType
    target: str
    is_satisfied: bool
    details: str
    is_optional: bool = False


def check_binary(binary_name: str, optional: bool = False) -> DependencyCheck:
    """Check if a system binary executable is available in PATH."""
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


def check_device_node(device_path: str, write_access: bool = False, optional: bool = False) -> DependencyCheck:
    """Check if a Linux device node exists and has required permissions."""
    path = Path(device_path)
    exists = path.exists()
    writable = os.access(device_path, os.W_OK) if exists else False
    satisfied = exists and (not write_access or writable)
    details = f"Device exists (writable: {writable})" if exists else f"Device node '{device_path}' does not exist"
    return DependencyCheck(
        dep_type=DependencyType.DEVICE_NODE,
        target=device_path,
        is_satisfied=satisfied,
        details=details,
        is_optional=optional,
    )


def check_socket(socket_path: str, optional: bool = False) -> DependencyCheck:
    """Check if an IPC UNIX socket is active."""
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


def check_python_module(module_name: str, optional: bool = False) -> DependencyCheck:
    """Check if a Python module can be imported in current environment."""
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


def check_python_dependency(req: str, optional: bool = False) -> DependencyCheck:
    """Audit a Python package requirement using uv pip compile dry-run resolution."""
    if uv_bin := shutil.which("uv"):
        try:
            res = subprocess.run(
                [uv_bin, "pip", "compile", "-", "-q"],
                input=req,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if res.returncode == 0:
                return DependencyCheck(
                    dep_type=DependencyType.PYTHON_MODULE,
                    target=req,
                    is_satisfied=True,
                    details=f"Package requirement '{req}' resolvable via uv PubGrub resolver",
                    is_optional=optional,
                )
            err = res.stderr.strip().splitlines()[-1] if res.stderr else "Resolution error"
            return DependencyCheck(
                dep_type=DependencyType.PYTHON_MODULE,
                target=req,
                is_satisfied=False,
                details=f"uv dependency conflict: {err}",
                is_optional=optional,
            )
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            logger.debug("seams.uv_dependency_compile_error", error=str(e))

    base_pkg = req
    for sep in ("==", ">=", "<=", "~="):
        base_pkg = base_pkg.split(sep, maxsplit=1)[0]
    base_pkg = base_pkg.strip()
    return check_python_module(base_pkg, optional=optional)


def check_env_variable(var_name: str, optional: bool = False) -> DependencyCheck:
    """Check if an environment variable is set and non-empty."""
    val = os.environ.get(var_name)
    if val is not None and len(val.strip()) > 0:
        details = f"Set (len={len(val)})"
        satisfied = True
    else:
        details = f"Environment variable '{var_name}' is unset or empty"
        satisfied = False
    return DependencyCheck(
        dep_type=DependencyType.ENV_VARIABLE,
        target=var_name,
        is_satisfied=satisfied,
        details=details,
        is_optional=optional,
    )


def evaluate_dependencies(yarn: Any) -> list[DependencyCheck]:
    """Evaluate all system binary, device, socket, module, and env dependencies declared by a Yarn."""
    results: list[DependencyCheck] = []
    for dep in yarn.get_dependencies():
        dtype = dep.get("type")
        target = dep.get("target", "")
        optional = dep.get("optional", False)

        if dtype == DependencyType.SYSTEM_BINARY.value:
            results.append(check_binary(target, optional))
        elif dtype == DependencyType.DEVICE_NODE.value:
            results.append(
                check_device_node(target, write_access=dep.get("writable", False), optional=optional)
            )
        elif dtype == DependencyType.SOCKET_PATH.value:
            results.append(check_socket(target, optional))
        elif dtype == DependencyType.PYTHON_MODULE.value:
            results.append(check_python_module(target, optional))
        elif dtype == DependencyType.ENV_VARIABLE.value:
            results.append(check_env_variable(target, optional))

    if hasattr(yarn, "get_python_dependencies"):
        results.extend(
            check_python_dependency(p_dep)
            for p_dep in yarn.get_python_dependencies()
        )
    return results
