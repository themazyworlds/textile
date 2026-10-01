import contextlib
import inspect
import logging
import sys
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from textile.core.definitions.manifest import YarnManifest
from textile.core.execution.reflector import (
    StrandConfig,
    build_dynamic_strand,
    reflect_strands,
    reflect_wefts,
)
from textile.core.execution.strands import Strand, Weft
from textile.core.telemetry.elastic import EventUrgency, elastic
from textile.core.telemetry.tapestry import sensory_tapestry

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EventOptions:
    data: Any = None
    summary: str = ""
    urgency: EventUrgency = EventUrgency.NOTICE
    retained_slot: str | None = None
    retained_value: Any = None


class Yarn(ABC):
    """Abstract Base Class for all Textile Capability Yarns."""

    manifest: YarnManifest

    def __init__(self, manifest: YarnManifest | None = None) -> None:
        if manifest is not None:
            self.manifest = manifest
            return

        mod_file = getattr(
            sys.modules.get(self.__class__.__module__), "__file__", None
        )
        if not mod_file:
            with contextlib.suppress(TypeError, OSError):
                mod_file = inspect.getfile(self.__class__)

        if mod_file:
            p = Path(mod_file)
            toml_file = p.with_suffix(".toml")
            if not toml_file.exists():
                toml_file = p.parent / "yarn.toml"
            if toml_file.exists():
                self.manifest = YarnManifest.from_toml(toml_file)
                return

        raise FileNotFoundError(
            f"Validation Hint: Yarn '{self.__class__.__name__}' requires a valid TOML manifest file "
            "(<name>.toml or yarn.toml)."
        )

    def __getattr__(self, name: str) -> Any:
        manifest = self.__dict__.get("manifest")
        if manifest is not None and hasattr(manifest, name):
            return getattr(manifest, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        manifest = self.__dict__.get("manifest")
        if name != "manifest" and manifest is not None and hasattr(manifest, name):
            setattr(manifest, name, value)
        else:
            super().__setattr__(name, value)

    def get_python_dependencies(self) -> list[str]:
        """Return declared external Python package requirements for isolated uv execution."""
        return list(self.python_dependencies)

    @property
    def elastic(self):
        """Universal cross-process event and sensory bus."""
        return elastic

    @property
    def tapestry(self):
        """Universal live state & sensory blackboard."""
        return sensory_tapestry

    def publish_event(
        self,
        topic: str,
        options: EventOptions | None = None,
        **kwargs: Any,
    ) -> None:
        """Publish a real-time event to Elastic."""
        opts = options or EventOptions(**kwargs)
        self.elastic.broadcast(
            topic=topic,
            source=self.name,
            summary=opts.summary or f"Event '{topic}' from yarn '{self.name}'",
            urgency=opts.urgency,
            data=(
                opts.data
                if isinstance(opts.data, dict)
                else {"payload": opts.data}
            ),
            retained_slot=opts.retained_slot,
            retained_value=opts.retained_value,
        )

    def stitch(self, level: str, message: str, data: dict[str, Any] | None = None) -> Any:
        """Stitch a structured notice/alert into the Tapestry sensory blackboard."""
        return self.tapestry.stitch(level=level, source=self.name, message=message, data=data)

    def set_slot(self, key: str, value: Any) -> None:
        """Set a retained domain state slot in Elastic and Tapestry."""
        self.elastic.occupy_seat(key, value, source=self.name)

    def get_slot(self, key: str, default: Any = None) -> Any:
        """Get a retained domain state slot from Elastic."""
        return self.elastic.get_slot(key, default)

    def get_dependencies(self) -> list[dict[str, Any]]:
        """Return system dependency manifests declared for this yarn."""
        return getattr(self, "dependencies", [])

    def is_available(self) -> bool:
        """Check if runtime dependencies and environment are met. Defaults to True."""
        return True

    @cached_property
    def strands(self) -> list[Strand]:
        """Automatically discovers all @strand decorated methods on the class."""
        return reflect_strands(self)

    def get_strands(self) -> list[Strand]:
        return self.strands

    @cached_property
    def wefts(self) -> list[Weft]:
        """Automatically discovers all @weft decorated methods on the class."""
        return reflect_wefts(self)

    def get_wefts(self) -> list[Weft]:
        return self.wefts

    def build_strand(
        self,
        name: str,
        description: str,
        handler: Callable[[dict[str, Any]], Any],
        config: StrandConfig | None = None,
        **kwargs: Any,
    ) -> Strand:
        """Helper to build a Strand dynamically."""
        return build_dynamic_strand(self, name, description, handler, config, **kwargs)

    def execute_sync(self, strand_name: str, args: dict[str, Any]) -> str:
        """Execute strand synchronously by matching name in discovered strands."""
        return next(
            (
                s.handler(args)
                for s in self.get_strands()
                if s.name == strand_name and s.handler is not None
            ),
            f"Error: Strand '{strand_name}' not implemented in yarn '{self.name}'.",
        )

    def on_load(self) -> None:
        """Lifecycle hook invoked when the yarn is initialized and loaded into Loom."""

    def on_unload(self) -> None:
        """Lifecycle hook invoked when the yarn is unloaded from Loom."""

