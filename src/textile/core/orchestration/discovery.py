"""
Textile Yarn Discovery Subsystem.
Discovers Yarn entrypoints across XDG search paths and probes isolated venvs.
"""

import contextlib
import os
import subprocess
from pathlib import Path
from typing import Any

import orjson
import platformdirs
from needle import CapabilityTier, Strand, Yarn
from needle import parse_capability_tier as _parse_tier

from textile.core.execution.runner import execute_strand
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "ProbedYarn",
    "find_yarn_files",
    "get_probe_cache_file",
    "get_yarn_search_paths",
    "read_probe_cache",
    "try_probe_isolated_yarn",
    "write_probe_cache",
]


class ProbedYarn(Yarn):
    """Dynamically created Yarn representing a capability package probed in an isolated venv."""

    def __init__(
        self,
        name: str,
        description: str,
        layer: int,
        source_file: Path,
        meta: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        super().__init__(name=name, description=description, layer=layer, **kwargs)
        self._source_file = source_file
        self._class_name = meta.get("class_name", self.__class__.__name__)
        self._probed_strands_data = meta.get("strands", [])
        self._cached_strands: list[Strand] | None = None

    def get_strands(self) -> list[Strand]:
        if self._cached_strands is not None:
            return self._cached_strands

        strands: list[Strand] = []
        for s_data in self._probed_strands_data:
            s_name = s_data["name"]
            tier_val = _parse_tier(s_data.get("tier", CapabilityTier.INTERACT), s_name)
            params = s_data.get("parameters", {})
            req_list = s_data.get("required", [])
            strand_desc = s_data.get("description", s_name)
            no_timeout = bool(s_data.get("no_timeout", False))
            timeout = None if no_timeout else s_data.get("timeout", 30.0)

            async def _handler(args: dict[str, Any], _sname=s_name, _tier=tier_val, _timeout=timeout) -> str:
                return execute_strand(
                    self,
                    _sname,
                    args,
                    tier=_tier,
                    timeout=_timeout,
                )

            strands.append(
                Strand(
                    name=s_name,
                    description=strand_desc,
                    parameters=params,
                    required=req_list,
                    handler=_handler,
                    raw_handler=_handler,
                    capability=s_data.get("capability"),
                    tier=tier_val,
                )
            )

        self._cached_strands = strands
        return strands


def get_yarn_search_paths(config_dir: Path | None = None) -> list[Path]:
    """Retrieve ordered list of filesystem search paths for yarn discovery using platformdirs."""
    paths: list[Path] = []

    # 1. Explicit environment variable override
    env_paths = os.environ.get("TEXTILE_YARN_PATH")
    if env_paths:
        for p in env_paths.split(":"):
            if p.strip():
                paths.append(Path(p.strip()).expanduser().resolve())

    # 2. User custom / override directory (~/.config/textile/yarns)
    user_config = config_dir or (Path(platformdirs.user_config_dir("textile")) / "yarns")
    paths.append(user_config.expanduser().resolve())

    # 3. User installed plugins directory (~/.local/share/textile/yarns)
    user_data = Path(platformdirs.user_data_dir("textile")) / "yarns"
    paths.append(user_data.expanduser().resolve())

    # 4. System-wide installed directories (/usr/local/share/textile/yarns, /usr/share/textile/yarns)
    site_dirs = platformdirs.site_data_dir("textile", multipath=True)
    for site_dir in site_dirs.split(":"):
        if site_dir.strip():
            paths.append((Path(site_dir.strip()) / "yarns").resolve())

    # 5. Sibling textile-yarns repo or workspace dev directory (if running from git source tree)
    with contextlib.suppress(Exception):
        sibling_yarns = Path(__file__).resolve().parents[5] / "textile-yarns" / "yarns"
        if sibling_yarns.exists():
            paths.append(sibling_yarns.resolve())
        repo_yarns = Path(__file__).resolve().parents[4] / "yarns"
        if repo_yarns.exists():
            paths.append(repo_yarns.resolve())

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique_paths.append(path)

    return unique_paths


def get_probe_cache_file() -> Path:
    cache_dir = Path(platformdirs.user_cache_dir("textile"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "probed_yarns_cache.json"


def read_probe_cache() -> dict[str, Any]:
    cache_file = get_probe_cache_file()
    if not cache_file.exists():
        return {}
    with contextlib.suppress(OSError, orjson.JSONDecodeError):
        return orjson.loads(cache_file.read_bytes())
    return {}


def write_probe_cache(cache: dict[str, Any]) -> None:
    cache_file = get_probe_cache_file()
    with contextlib.suppress(OSError, orjson.JSONEncodeError):
        tmp_file = cache_file.with_suffix(".tmp")
        tmp_file.write_bytes(orjson.dumps(cache, option=orjson.OPT_INDENT_2))
        tmp_file.replace(cache_file)


def find_yarn_files(target_dir: Path) -> list[Path]:
    """Discover Yarn Python entrypoint files in target_dir without scanning site-packages."""
    candidates: list[Path] = []
    with contextlib.suppress(OSError):
        for entry in target_dir.iterdir():
            if entry.name.startswith((".", "_")):
                continue
            if entry.is_file() and entry.suffix == ".py":
                candidates.append(entry)
            elif entry.is_dir() and entry.name not in {
                ".venv",
                "venv",
                "__pycache__",
                "site-packages",
                "node_modules",
                "dist",
                "build",
            }:
                clean_name = entry.name.removeprefix("textile-yarn-").removeprefix("yarn-")
                named_py = entry / f"{entry.name}.py"
                clean_py = entry / f"{clean_name}.py"
                init_py = entry / "__init__.py"

                if named_py.is_file():
                    candidates.append(named_py)
                elif clean_py.is_file():
                    candidates.append(clean_py)
                elif init_py.is_file():
                    candidates.append(init_py)
    return candidates


def try_probe_isolated_yarn(py_file: Path) -> ProbedYarn | None:
    """Attempt to discover Yarn using its private virtualenv probe with schema disk cache."""
    yarn_venv_py = py_file.parent / ".venv" / "bin" / "python"
    if not yarn_venv_py.exists():
        return None

    resolved_path = py_file.resolve()
    path_str = str(resolved_path)
    try:
        mtime = resolved_path.stat().st_mtime
    except OSError:
        return None

    cache = read_probe_cache()
    cached_entry = cache.get(path_str)
    if cached_entry and cached_entry.get("mtime") == mtime and "probe_data" in cached_entry:
        data = cached_entry["probe_data"]
        return ProbedYarn(
            name=data["name"],
            description=data["description"],
            layer=data["layer"],
            source_file=resolved_path,
            meta=data,
            tailor=data.get("tailor", "textile"),
            version=data.get("version", "1.0.0"),
            resources=data.get("resources", []),
        )

    try:
        res = subprocess.run(
            [
                str(yarn_venv_py),
                "-m",
                "needle.manifest",
                path_str,
            ],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
        for line in res.stdout.splitlines():
            if line.startswith("__TEXTILE_PROBE_JSON__:"):
                raw_json = line.removeprefix("__TEXTILE_PROBE_JSON__:")
                data = orjson.loads(raw_json)
                probed_inst = ProbedYarn(
                    name=data["name"],
                    description=data["description"],
                    layer=data["layer"],
                    source_file=resolved_path,
                    meta=data,
                    tailor=data.get("tailor", "textile"),
                    version=data.get("version", "1.0.0"),
                    resources=data.get("resources", []),
                )
                cache[path_str] = {"mtime": mtime, "probe_data": data}
                write_probe_cache(cache)
                return probed_inst
        return None
    except (subprocess.SubprocessError, OSError, orjson.JSONDecodeError) as e:
        logger.debug("skein.yarn_venv_probe_failed", path=str(py_file), error=str(e))
        return None
