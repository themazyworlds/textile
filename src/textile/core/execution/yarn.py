import asyncio
import concurrent.futures
import contextlib
import inspect
import logging
import tomllib
from abc import ABC
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from textile.core.definitions.errors import SAFE_EXCEPTIONS
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

    name: str = ""
    description: str = ""
    layer: int = 10
    publisher: str = "textile"
    version: str = "1.0.0"
    resources: Sequence[str] = ()
    settings_schema: type[BaseModel] | None = None
    dependencies: Sequence[str] = ()

    def __init__(
        self,
        name: str | None = None,
        description: str | None = None,
        layer: int | None = None,
        **kwargs: Any,
    ) -> None:
        if name:
            self.name = name
        elif not self.name:
            self.name = self.__class__.__name__.lower()

        if description:
            self.description = description
        elif not self.description:
            doc = inspect.getdoc(self.__class__)
            self.description = doc.splitlines()[0] if doc else self.name

        if layer is not None:
            self.layer = layer
        if "publisher" in kwargs and kwargs["publisher"] is not None:
            self.publisher = str(kwargs["publisher"])
        if "version" in kwargs and kwargs["version"] is not None:
            self.version = str(kwargs["version"])
        if "resources" in kwargs and kwargs["resources"] is not None:
            self.resources = list(kwargs["resources"])
        if "dependencies" in kwargs and kwargs["dependencies"] is not None:
            self.dependencies = list(kwargs["dependencies"])

        self._populate_pyproject_metadata(name=name, description=description, layer=layer, kwargs=kwargs)
        self._settings: Any = None

    def _populate_pyproject_metadata(
        self,
        name: str | None,
        description: str | None,
        layer: int | None,
        kwargs: dict[str, Any],
    ) -> None:
        with contextlib.suppress(*SAFE_EXCEPTIONS):
            mod_file = inspect.getfile(self.__class__)
            if not mod_file:
                return
            pyproj = Path(mod_file).parent / "pyproject.toml"
            if not pyproj.exists():
                return
            with pyproj.open("rb") as f:
                data = tomllib.load(f)
            self._apply_project_table(data.get("project", {}), name, description, kwargs)
            self._apply_tool_table(data.get("tool", {}).get("textile", {}), layer, kwargs)

    def _apply_project_table(
        self,
        project: dict[str, Any],
        name: str | None,
        description: str | None,
        kwargs: dict[str, Any],
    ) -> None:
        if not name and "name" in project and (not self.name or self.name == self.__class__.__name__.lower()):
            raw_name = str(project["name"])
            self.name = raw_name.removeprefix("textile-yarn-").removeprefix("yarn-")
        if not description and "description" in project and (not self.description or self.description == self.name):
            self.description = str(project["description"])
        if "version" not in kwargs and "version" in project:
            self.version = str(project["version"])
        if "authors" in project and project["authors"] and "publisher" not in kwargs:
            first_author = project["authors"][0]
            if isinstance(first_author, dict):
                self.publisher = str(first_author.get("name", "textile"))
            else:
                self.publisher = str(first_author)
        if "dependencies" not in kwargs and not self.dependencies and "dependencies" in project:
            self.dependencies = list(project["dependencies"])

    def _apply_tool_table(
        self,
        tool_textile: dict[str, Any],
        layer: int | None,
        kwargs: dict[str, Any],
    ) -> None:
        if layer is None and "layer" in tool_textile:
            self.layer = int(tool_textile["layer"])
        if "resources" not in kwargs and not self.resources and "resources" in tool_textile:
            self.resources = list(tool_textile["resources"])

    def get_settings_schema(self) -> type[BaseModel] | None:
        """Return explicit Pydantic settings schema for this yarn."""
        return self.settings_schema

    @property
    def settings(self) -> Any:
        """Returns validated settings for this yarn based on settings_schema and ~/.config/textile/settings.toml."""
        if self._settings is not None:
            return self._settings

        user_config = get_user_yarn_settings(self.name)
        schema = self.get_settings_schema()
        if schema is not None and isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                self._settings = schema.model_validate(user_config)
            except ValidationError as e:
                logger.warning(
                    "yarn.settings_validation_failed: %s (error: %s). Falling back to schema defaults.",
                    self.name,
                    str(e),
                )
                try:
                    self._settings = schema()
                except SAFE_EXCEPTIONS:
                    self._settings = user_config
        else:
            self._settings = user_config

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

    def get_dependencies(self) -> list[str]:
        """Return system dependencies declared for this yarn."""
        return list(getattr(self, "dependencies", []))

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
