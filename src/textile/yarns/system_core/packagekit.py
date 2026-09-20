"""
Linux Universal Package Management Capability Yarn for Textile via PackageKit D-Bus IPC.
Provides distribution-agnostic package search, installation, removal, update checks,
and file provider queries via the freedesktop.org PackageKit D-Bus protocol (org.freedesktop.PackageKit).
Layer 10 (Core POSIX / System Lifecycle).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dbus_fast import BusType, Variant
    from dbus_fast.aio import MessageBus
else:
    try:
        from dbus_fast import BusType, Variant
        from dbus_fast.aio import MessageBus
    except ImportError:
        BusType = Any
        Variant = Any
        MessageBus = Any

from textile.core.base import CapabilityTier, Yarn, strand

logger = logging.getLogger(__name__)

PKG_ID_MIN_PARTS_ARCH = 2
PKG_ID_MIN_PARTS_REPO = 3
CACHE_FRESH_SECONDS = 60.0


def parse_package_id(package_id: str) -> dict[str, str]:
    """Parse a standard PackageKit package_id string (name;version;arch;data)."""
    pkg_id = package_id
    parts = pkg_id.split(";")
    return {
        "id": pkg_id,
        "name": parts[0] if len(parts) > 0 else pkg_id,
        "version": parts[1] if len(parts) > 1 else "",
        "arch": parts[2] if len(parts) > PKG_ID_MIN_PARTS_ARCH else "",
        "repository": parts[3] if len(parts) > PKG_ID_MIN_PARTS_REPO else "",
    }


def unwrap_variant(val: Any) -> Any:
    """Recursively unwrap dbus_fast Variant values to native Python types."""
    if hasattr(val, "value") and type(val).__name__ == "Variant":
        return unwrap_variant(getattr(val, "value"))
    elif isinstance(val, dict):
        return {str(k): unwrap_variant(v) for k, v in val.items()}
    elif isinstance(val, (list, tuple)):
        return [unwrap_variant(x) for x in val]
    return val


class PackageKitDBusClient:
    """High-speed native D-Bus client for org.freedesktop.PackageKit."""

    def __init__(self):
        self._system_bus: MessageBus | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._updates_cache: list[dict[str, Any]] | None = None
        self._updates_cache_time: float = 0.0
        self._updates_in_progress: bool = False
        self._updates_event: asyncio.Event | None = None
        self._refresh_in_progress: bool = False
        self._refresh_event: asyncio.Event | None = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="packagekit-dbus")
                self._thread.start()
            return self._loop

    def run_sync(self, coro, timeout: float = 60.0) -> Any:
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    async def _get_bus(self) -> Any:
        if self._system_bus is None and callable(MessageBus):
            mb_cls: Any = MessageBus
            self._system_bus = await mb_cls(bus_type=BusType.SYSTEM).connect()
        return self._system_bus

    async def _create_transaction(self) -> tuple[Any, Any]:
        """Create a transient PackageKit transaction and return (proxy, interface)."""
        bus = await self._get_bus()
        intro = await bus.introspect("org.freedesktop.PackageKit", "/org/freedesktop/PackageKit")
        pk_proxy = bus.get_proxy_object("org.freedesktop.PackageKit", "/org/freedesktop/PackageKit", intro)
        pk_iface = pk_proxy.get_interface("org.freedesktop.PackageKit")
        tx_path = await pk_iface.call_create_transaction()
        tx_intro = await bus.introspect("org.freedesktop.PackageKit", tx_path)
        tx_proxy = bus.get_proxy_object("org.freedesktop.PackageKit", tx_path, tx_intro)
        tx_iface = tx_proxy.get_interface("org.freedesktop.PackageKit.Transaction")
        return tx_proxy, tx_iface

    async def search_names(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        """Search packages via direct D-Bus Transaction SearchNames."""
        _, tx = await self._create_transaction()
        results: list[dict[str, Any]] = []
        errors: list[str] = []
        finished = asyncio.Event()

        def on_package(info: int, pkg_id: str, summary: str):
            meta = parse_package_id(pkg_id)
            meta["summary"] = summary
            meta["info_code"] = str(info)
            results.append(meta)

        def on_error(code: int, details: str):
            errors.append(f"PackageKit Error {code}: {details}")

        def on_finished(exit_code: int, runtime: int):
            finished.set()

        tx.on_package(on_package)
        tx.on_error_code(on_error)
        tx.on_finished(on_finished)

        await tx.call_search_names(0, [query])
        await asyncio.wait_for(finished.wait(), timeout=30.0)

        if errors and not results:
            return [{"error": e} for e in errors]
        return results[:limit]

    async def resolve(self, package_names: list[str]) -> list[dict[str, Any]]:
        """Resolve package names to PackageKit package_ids."""
        _, tx = await self._create_transaction()
        results: list[dict[str, Any]] = []
        finished = asyncio.Event()

        def on_package(info: int, pkg_id: str, summary: str):
            meta = parse_package_id(pkg_id)
            meta["summary"] = summary
            results.append(meta)

        def on_finished(exit_code: int, runtime: int):
            finished.set()

        tx.on_package(on_package)
        tx.on_finished(on_finished)

        await tx.call_resolve(0, package_names)
        await asyncio.wait_for(finished.wait(), timeout=20.0)
        return results

    async def get_details(self, package_name: str) -> dict[str, Any]:
        """Retrieve package metadata via D-Bus GetDetails."""
        resolved = await self.resolve([package_name])
        if not resolved:
            search_res = await self.search_names(package_name, limit=1)
            if not search_res or "error" in search_res[0]:
                return {"error": f"Package '{package_name}' not found."}
            pkg_id = search_res[0]["id"]
        else:
            pkg_id = resolved[0]["id"]

        _, tx = await self._create_transaction()
        details_map: dict[str, Any] = {"package": package_name, "id": pkg_id}
        finished = asyncio.Event()

        def on_details(raw_dict: Any):
            unwrapped = unwrap_variant(raw_dict)
            if isinstance(unwrapped, dict):
                details_map.update(unwrapped)

        def on_finished(exit_code: int, runtime: int):
            finished.set()

        tx.on_details(on_details)
        tx.on_finished(on_finished)

        await tx.call_get_details([pkg_id])
        await asyncio.wait_for(finished.wait(), timeout=20.0)
        return details_map

    async def _fetch_updates_task(self):
        """Asynchronously perform the full GetUpdates scan in the background."""
        try:
            _, tx = await self._create_transaction()
            updates: list[dict[str, Any]] = []
            finished = asyncio.Event()

            def on_package(info: int, pkg_id: str, summary: str):
                meta = parse_package_id(pkg_id)
                meta["summary"] = summary
                updates.append(meta)

            def on_finished(exit_code: int, runtime: int):
                finished.set()

            def on_error(code: int, details: str):
                finished.set()

            tx.on_package(on_package)
            tx.on_finished(on_finished)
            tx.on_error_code(on_error)

            await tx.call_get_updates(0)
            await asyncio.wait_for(finished.wait(), timeout=180.0)
            self._updates_cache = updates
            self._updates_cache_time = time.time()
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.debug(f"Background GetUpdates failed: {e}")
        finally:
            self._updates_in_progress = False
            if self._updates_event:
                self._updates_event.set()

    async def get_updates(self, max_wait: float = 2.5) -> list[dict[str, Any]]:
        """Check for pending updates with background caching and MCP timeout protection."""
        now = time.time()

        # If cache is very fresh (<60s) and no scan in progress, return immediately
        if (
            self._updates_cache is not None
            and (now - self._updates_cache_time < CACHE_FRESH_SECONDS)
            and not self._updates_in_progress
        ):
            return self._updates_cache

        # Start scan in background if not already running
        if not self._updates_in_progress:
            self._updates_in_progress = True
            self._updates_event = asyncio.Event()
            asyncio.create_task(self._fetch_updates_task())

        # Wait up to max_wait seconds for the scan to complete
        if self._updates_event:
            try:
                await asyncio.wait_for(self._updates_event.wait(), timeout=max_wait)
                if self._updates_cache is not None:
                    return self._updates_cache
            except TimeoutError:
                pass

        # If scan took longer than max_wait: return cached updates if available, or informative progress state
        if self._updates_cache is not None:
            return self._updates_cache

        return [{
            "status": "scan_in_progress",
            "notice": (
                "Package updates check started in background. "
                "Query again in a few seconds."
            ),
        }]

    async def what_provides(self, file_path: str) -> str:
        """Find packages providing a capability or file."""
        _, tx = await self._create_transaction()
        providers: list[str] = []
        finished = asyncio.Event()

        def on_package(info: int, pkg_id: str, summary: str):
            providers.append(pkg_id)

        def on_finished(exit_code: int, runtime: int):
            finished.set()

        tx.on_package(on_package)
        tx.on_finished(on_finished)

        await tx.call_what_provides(0, [file_path])
        await asyncio.wait_for(finished.wait(), timeout=30.0)

        if not providers:
            return f"No package found providing '{file_path}'."
        return "\n".join(providers)

    async def _fetch_refresh_task(self, force: bool):
        """Background repository cache refresh."""
        try:
            _, tx = await self._create_transaction()
            finished = asyncio.Event()
            tx.on_finished(lambda code, rt: finished.set())
            tx.on_error_code(lambda code, det: finished.set())
            await tx.call_refresh_cache(force)
            await asyncio.wait_for(finished.wait(), timeout=180.0)
            self._updates_cache = None  # Invalidate cached updates
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            logger.debug(f"Background refresh_cache failed: {e}")
        finally:
            self._refresh_in_progress = False
            if self._refresh_event:
                self._refresh_event.set()

    async def refresh_cache(self, force: bool = False, max_wait: float = 2.5) -> str:
        """Refresh repository metadata cache with non-blocking MCP safety."""
        if not self._refresh_in_progress:
            self._refresh_in_progress = True
            self._refresh_event = asyncio.Event()
            asyncio.create_task(self._fetch_refresh_task(force))

        if self._refresh_event:
            try:
                await asyncio.wait_for(self._refresh_event.wait(), timeout=max_wait)
                return "Package repository cache refreshed successfully via PackageKit D-Bus."
            except TimeoutError:
                pass

        return "Package repository cache refresh initiated in background. You can check updates once complete."

    async def install_packages(self, package_names: list[str]) -> str:
        """Install packages via D-Bus InstallPackages."""
        resolved = await self.resolve(package_names)
        if not resolved:
            return f"Error: Could not resolve package names: {', '.join(package_names)}"

        pkg_ids = [r["id"] for r in resolved]
        _, tx = await self._create_transaction()
        errors: list[str] = []
        finished = asyncio.Event()

        def on_error(code: int, details: str):
            errors.append(f"Error {code}: {details}")

        def on_finished(exit_code: int, runtime: int):
            finished.set()

        tx.on_error_code(on_error)
        tx.on_finished(on_finished)

        await tx.call_install_packages(0, pkg_ids)
        await asyncio.wait_for(finished.wait(), timeout=300.0)

        if errors:
            return f"Installation error: {'; '.join(errors)}"
        return f"Successfully installed: {', '.join(package_names)}"

    async def remove_packages(self, package_names: list[str], autoremove: bool = False) -> str:
        """Remove packages via D-Bus RemovePackages."""
        resolved = await self.resolve(package_names)
        if not resolved:
            return f"Error: Could not resolve package names: {', '.join(package_names)}"

        pkg_ids = [r["id"] for r in resolved]
        _, tx = await self._create_transaction()
        errors: list[str] = []
        finished = asyncio.Event()

        def on_error(code: int, details: str):
            errors.append(f"Error {code}: {details}")

        def on_finished(exit_code: int, runtime: int):
            finished.set()

        tx.on_error_code(on_error)
        tx.on_finished(on_finished)

        await tx.call_remove_packages(0, pkg_ids, True, autoremove)
        await asyncio.wait_for(finished.wait(), timeout=300.0)

        if errors:
            return f"Removal error: {'; '.join(errors)}"
        return f"Successfully removed: {', '.join(package_names)}"


class PackageKitController:
    """D-Bus Controller for PackageKit."""

    def __init__(self):
        self.client = PackageKitDBusClient() if MessageBus is not None else None

    def is_available(self) -> bool:
        return self.client is not None

    def search(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        if self.client is None:
            return [{"error": "PackageKit D-Bus client is not available."}]
        clean_query = query.strip()
        if not clean_query:
            return []
        try:
            return self.client.run_sync(self.client.search_names(clean_query, limit=limit), timeout=30.0)
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            return [{"error": f"PackageKit D-Bus search error: {e}"}]

    def install(self, packages: list[str]) -> str:
        if self.client is None:
            return "Error: PackageKit D-Bus client is not available."
        if not packages:
            return "Error: No packages specified for installation."
        try:
            return self.client.run_sync(self.client.install_packages(packages), timeout=300.0)
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            return f"PackageKit D-Bus install error: {e}"

    def remove(self, packages: list[str], autoremove: bool = False) -> str:
        if self.client is None:
            return "Error: PackageKit D-Bus client is not available."
        if not packages:
            return "Error: No packages specified for removal."
        try:
            return self.client.run_sync(self.client.remove_packages(packages, autoremove=autoremove), timeout=300.0)
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            return f"PackageKit D-Bus remove error: {e}"

    def get_details(self, package: str) -> dict[str, Any]:
        if self.client is None:
            return {"error": "PackageKit D-Bus client is not available."}
        pkg_name = package.strip()
        try:
            return self.client.run_sync(self.client.get_details(pkg_name), timeout=25.0)
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            return {"error": f"PackageKit D-Bus get_details error: {e}"}

    def check_updates(self) -> list[dict[str, Any]]:
        if self.client is None:
            return [{"error": "PackageKit D-Bus client is not available."}]
        try:
            return self.client.run_sync(self.client.get_updates(max_wait=3.5), timeout=4.5)
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            return [{"error": f"PackageKit D-Bus check_updates error: {e}"}]

    def what_provides(self, file_path: str) -> str:
        if self.client is None:
            return "Error: PackageKit D-Bus client is not available."
        try:
            return self.client.run_sync(self.client.what_provides(file_path), timeout=30.0)
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            return f"PackageKit D-Bus what_provides error: {e}"

    def refresh_cache(self, force: bool = False) -> str:
        if self.client is None:
            return "Error: PackageKit D-Bus client is not available."
        try:
            return self.client.run_sync(self.client.refresh_cache(force=force, max_wait=2.5), timeout=3.5)
        except (OSError, RuntimeError, ValueError, TypeError, AttributeError, KeyError) as e:
            return f"PackageKit D-Bus refresh_cache error: {e}"


packagekit_ctl = PackageKitController()


class PackageKit(Yarn):
    """Universal Linux Package Management Capability Yarn via PackageKit D-Bus IPC."""

    def is_available(self) -> bool:
        return packagekit_ctl.is_available()

    @strand(
        description="Search for available or installed packages via PackageKit D-Bus.",
        tier=CapabilityTier.OBSERVE,
    )
    def packagekit_search(self, query: str = "", limit: int = 25) -> list[dict[str, Any]]:
        """Search packages by name or keyword across distribution repositories.

        :param query: Package name or search keyword (e.g. 'neovim', 'ripgrep', 'htop').
        :param limit: Maximum number of package results to return.
        """
        return packagekit_ctl.search(query=query, limit=limit)

    @strand(
        description="Install one or more packages non-interactively via PackageKit D-Bus with Polkit authorization.",
        tier=CapabilityTier.PRIVILEGED,
    )
    def packagekit_install(self, packages: str) -> str:
        """Install one or more packages.

        :param packages: Space- or comma-separated list of package names to install (e.g. 'htop ripgrep').
        """
        pkgs_raw = [p.strip() for p in packages.replace(",", " ").split() if p.strip()]
        return packagekit_ctl.install(packages=pkgs_raw)

    @strand(
        description="Remove one or more installed packages via PackageKit D-Bus.",
        tier=CapabilityTier.PRIVILEGED,
    )
    def packagekit_remove(self, packages: str, autoremove: bool = False) -> str:
        """Remove one or more packages.

        :param packages: Space- or comma-separated list of package names to remove.
        :param autoremove: Automatically remove unused dependencies.
        """
        pkgs_raw = [p.strip() for p in packages.replace(",", " ").split() if p.strip()]
        return packagekit_ctl.remove(packages=pkgs_raw, autoremove=autoremove)

    @strand(
        description="Get package metadata, description, license, and repo info via PackageKit D-Bus.",
        tier=CapabilityTier.OBSERVE,
    )
    def packagekit_get_details(self, package: str) -> dict[str, Any]:
        """Get detailed metadata for a package.

        :param package: Name of package to inspect (e.g. 'firefox', 'python').
        """
        return packagekit_ctl.get_details(package=package)

    @strand(
        description="Check for pending package and system software updates via PackageKit D-Bus.",
        tier=CapabilityTier.OBSERVE,
    )
    def packagekit_check_updates(self) -> list[dict[str, Any]]:
        """Check for pending system updates."""
        return packagekit_ctl.check_updates()

    @strand(
        description="Find which package provides a specific file path or binary via PackageKit D-Bus.",
        tier=CapabilityTier.OBSERVE,
    )
    def packagekit_what_provides(self, file_path: str) -> str:
        """Find package providing a specific file.

        :param file_path: Absolute path or binary name (e.g. '/usr/bin/git', 'libssl.so').
        """
        return packagekit_ctl.what_provides(file_path=file_path)

    @strand(
        description="Refresh package manager repository metadata cache via PackageKit D-Bus.",
        tier=CapabilityTier.PRIVILEGED,
    )
    def packagekit_refresh_cache(self, force: bool = False) -> str:
        """Refresh package repository cache.

        :param force: Force download of all repository databases.
        """
        return packagekit_ctl.refresh_cache(force=force)

