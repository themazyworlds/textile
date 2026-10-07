import asyncio
import concurrent.futures
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

from pydantic import BaseModel, ValidationError

from textile.core.definitions.manifest import YarnManifest
from textile.core.definitions.settings import get_user_yarn_settings
from textile.core.execution.reflector import (
    StrandConfig,
    build_dynamic_strand,
    reflect_strands,
    reflect_wefts,
)
from textile.core.execution.strands import Strand, Weft
from textile.core.telemetry.blackboard import sensory_tapestry
from textile.core.telemetry.elastic import EventUrgency, elastic

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
    settings_schema: type[BaseModel] | None = None

    def __init__(self, manifest: YarnManifest | None = None) -> None:
        self._settings: Any = None
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

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def description(self) -> str:
        return self.manifest.description

    @property
    def layer(self) -> int:
        return self.manifest.layer

    @property
    def publisher(self) -> str:
        return self.manifest.publisher

    @property
    def python_dependencies(self) -> list[str]:
        return list(self.manifest.python_dependencies)

    def get_python_dependencies(self) -> list[str]:
        """Return declared external Python package requirements for isolated uv execution."""
        return list(self.manifest.python_dependencies)

    def get_settings_schema(self) -> type[BaseModel] | None:
        """Return explicit or dynamically-generated Pydantic settings schema for this yarn."""
        if self.settings_schema is not None:
            return self.settings_schema
        if hasattr(self, "manifest") and self.manifest.settings:
            return self.manifest.create_settings_model()
        return None

    @property
    def settings(self) -> Any:
        """Returns validated settings for this yarn based on settings_schema and ~/.config/textile/settings.toml."""
        if self._settings is not None:
            return self._settings

        manifest_defaults = self.manifest.get_default_settings() if hasattr(self, "manifest") else {}
        user_config = get_user_yarn_settings(self.name)
        merged_config = {**manifest_defaults, **user_config}

        schema = self.get_settings_schema()
        if schema is not None and isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                self._settings = schema.model_validate(merged_config)
            except ValidationError as e:
                logger.warning(
                    "yarn.settings_validation_failed: %s (error: %s). Falling back to schema defaults.",
                    self.name,
                    str(e),
                )
                try:
                    self._settings = schema()
                except (ValidationError, TypeError, ValueError):
                    self._settings = merged_config
        else:
            self._settings = merged_config

        return self._settings

    def reload_settings(self) -> Any:
        """Clear cached settings and reload from Skein."""
        self._settings = None
        return self.settings

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
        """Automatically discovers all @strand decorated methods on the class once."""
        return reflect_strands(self)

    def get_strands(self) -> list[Strand]:
        return self.strands

    @cached_property
    def wefts(self) -> list[Weft]:
        """Automatically discovers all @weft decorated methods on the class once."""
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
        strand = next((s for s in self.get_strands() if s.name == strand_name and s.handler is not None), None)
        if not strand or not strand.handler:
            return f"Error: Strand '{strand_name}' not implemented in yarn '{self.name}'."

        res = strand.handler(args)
        if inspect.isawaitable(res):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return str(pool.submit(asyncio.run, res).result())
            return str(asyncio.run(res))
        return str(res)

    def on_load(self) -> None:
        """Lifecycle hook invoked when the yarn is initialized and loaded into Loom."""

    def on_unload(self) -> None:
        """Lifecycle hook invoked when the yarn is unloaded from Loom."""
