"""
Textile Yarn Discovery Subsystem.
Discovers Yarn entrypoints across XDG search paths and probes isolated venvs.
"""

import ast
import contextlib
import os
import tomllib
from pathlib import Path
from typing import Any

import orjson
import platformdirs
from needle import CapabilityTier, Strand, Yarn
from needle import parse_capability_tier as _parse_tier

from textile.core.execution.runner import execute_strand_async
from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

__all__ = [
    "ProbedYarn",
    "find_yarn_files",
    "get_probe_cache_file",
    "get_yarn_search_paths",
    "parse_yarn_manifest_ast",
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
                return await execute_strand_async(
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
                    resources=list(s_data.get("resources", [])),
                    timeout=timeout,
                    no_timeout=no_timeout,
                    reason=s_data.get("reason"),
                    fallback=s_data.get("fallback"),
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


def _parse_param_type(ann_str: str) -> str:
    clean = ann_str.split("|", maxsplit=1)[0].strip().lower() if ann_str else "str"
    if "int" in clean:
        return "integer"
    if "float" in clean:
        return "number"
    if "bool" in clean:
        return "boolean"
    if "list" in clean:
        return "array"
    if "dict" in clean:
        return "object"
    return "string"


def _extract_decorator_info(dec_node: ast.expr) -> tuple[str, dict[str, Any]]:
    if isinstance(dec_node, ast.Call):
        func_expr = ast.unparse(dec_node.func)
        kwargs: dict[str, Any] = {}
        for kw in dec_node.keywords:
            if kw.arg:
                with contextlib.suppress(Exception):
                    kwargs[kw.arg] = ast.literal_eval(kw.value)
                if kw.arg not in kwargs:
                    kwargs[kw.arg] = ast.unparse(kw.value)
        return func_expr, kwargs
    return ast.unparse(dec_node), {}


def _extract_strand_parameters(
    item: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[dict[str, Any], list[str]]:
    num_args = len(item.args.args)
    num_defaults = len(item.args.defaults)
    defaults: list[ast.expr | None] = [None] * (num_args - num_defaults) + list(item.args.defaults)

    params: dict[str, Any] = {}
    required: list[str] = []

    for arg_node, def_node in zip(item.args.args, defaults, strict=False):
        if arg_node.arg in {"self", "cls"}:
            continue
        ann_str = ast.unparse(arg_node.annotation) if arg_node.annotation else "str"
        prop: dict[str, Any] = {"type": _parse_param_type(ann_str)}
        if def_node is not None:
            with contextlib.suppress(Exception):
                prop["default"] = ast.literal_eval(def_node)
            if "default" not in prop:
                prop["default"] = ast.unparse(def_node)
        else:
            required.append(arg_node.arg)
        params[arg_node.arg] = prop

    return params, required


def _extract_strand_data(
    item: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, Any] | None:
    strand_dec: tuple[str, dict[str, Any]] | None = None
    for d in item.decorator_list:
        d_name, d_kwargs = _extract_decorator_info(d)
        if "strand" in d_name:
            strand_dec = (d_name, d_kwargs)
            break

    if strand_dec is None:
        return None

    dec_name, dec_kwargs = strand_dec
    tier = dec_kwargs.get("tier")
    if not tier:
        tier = dec_name.split(".")[-1].upper() if "." in dec_name else "INTERACT"

    method_doc = ast.get_docstring(item) or ""
    method_first_line = method_doc.splitlines()[0].strip() if method_doc else item.name
    desc = dec_kwargs.get("description") or method_first_line
    s_name = dec_kwargs.get("name") or item.name

    params, required = _extract_strand_parameters(item)
    no_timeout = bool(dec_kwargs.get("no_timeout", False))
    timeout = None if no_timeout else dec_kwargs.get("timeout")

    return {
        "name": s_name,
        "description": desc,
        "tier": str(tier),
        "parameters": params,
        "required": required,
        "timeout": timeout,
        "no_timeout": no_timeout,
        "capability": dec_kwargs.get("capability"),
        "resources": dec_kwargs.get("resources", []),
        "reason": dec_kwargs.get("reason"),
        "fallback": dec_kwargs.get("fallback"),
    }


def _read_accompanying_pyproject(py_file: Path) -> dict[str, Any]:
    pyproject_file = py_file.parent / "pyproject.toml"
    if not pyproject_file.is_file():
        return {}
    with contextlib.suppress(OSError, tomllib.TOMLDecodeError):
        toml_data = tomllib.loads(pyproject_file.read_text(encoding="utf-8"))
        proj_meta = toml_data.get("project", {})
        proj_meta.update(toml_data.get("tool", {}).get("textile", {}))
        return proj_meta
    return {}


def _inspect_class_body(
    node: ast.ClassDef,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    class_attrs: dict[str, Any] = {}
    strands_data: list[dict[str, Any]] = []

    for item in node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    with contextlib.suppress(Exception):
                        class_attrs[target.id] = ast.literal_eval(item.value)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name) and item.value:
            with contextlib.suppress(Exception):
                class_attrs[item.target.id] = ast.literal_eval(item.value)
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            strand_info = _extract_strand_data(item)
            if strand_info:
                strands_data.append(strand_info)

    return class_attrs, strands_data


def _build_yarn_manifest(
    node: ast.ClassDef,
    class_attrs: dict[str, Any],
    strands_data: list[dict[str, Any]],
    proj_meta: dict[str, Any],
) -> dict[str, Any]:
    class_doc = ast.get_docstring(node) or ""
    first_doc_line = class_doc.splitlines()[0].strip() if class_doc else ""

    raw_name = (
        class_attrs.get("name")
        or proj_meta.get("name", "").removeprefix("textile-yarn-").removeprefix("yarn-")
        or node.name.lower().removesuffix("yarn")
    )
    yarn_desc = class_attrs.get("description") or proj_meta.get("description") or first_doc_line or raw_name

    return {
        "class_name": node.name,
        "name": raw_name,
        "description": yarn_desc,
        "layer": int(class_attrs.get("layer", proj_meta.get("layer", 50))),
        "tailor": class_attrs.get("tailor", proj_meta.get("tailor", "textile")),
        "version": str(class_attrs.get("version", proj_meta.get("version", "1.0.0"))),
        "resources": list(class_attrs.get("resources", proj_meta.get("resources", []))),
        "strands": strands_data,
    }


def parse_yarn_manifest_ast(py_file: Path) -> dict[str, Any] | None:
    """Statically parse a Yarn source file and extract its manifest and strands without executing code."""
    try:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
    except OSError, SyntaxError, UnicodeDecodeError:
        return None

    proj_meta = _read_accompanying_pyproject(py_file)

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        is_yarn_class = any(
            (isinstance(b, ast.Name) and b.id == "Yarn") or (isinstance(b, ast.Attribute) and b.attr == "Yarn")
            for b in node.bases
        )

        class_attrs, strands_data = _inspect_class_body(node)
        if not is_yarn_class and not strands_data:
            continue

        return _build_yarn_manifest(node, class_attrs, strands_data, proj_meta)

    return None


def try_probe_isolated_yarn(py_file: Path) -> ProbedYarn | None:
    """Discover Yarn statically using pure-Python AST parsing with schema disk cache."""
    resolved_path = py_file.resolve()
    if not resolved_path.is_file():
        return None

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

    data = parse_yarn_manifest_ast(resolved_path)
    if not data:
        return None

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
