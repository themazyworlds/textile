"""
Universal Dynamic D-Bus Capability Yarn for Textile.
Exposes generic D-Bus RPC method execution, property reading/writing, and node introspection
across Session and System Busses without subprocess wrappers.
Layer 50 (Desktop Protocol).
"""

import asyncio
import json
import os
import threading
from typing import Any, Dict, List, Literal, Optional

try:
    from dbus_fast import BusType, Message, MessageFlag, MessageType, Variant
    from dbus_fast.aio import MessageBus
except Exception:
    BusType = Message = MessageFlag = MessageType = Variant = MessageBus = None

from textile.core.base import BaseYarn, strand, LAYER_DESKTOP_PROTOCOL


class DBusAPI:
    """Universal Dynamic D-Bus Client with persistent background event loop."""

    def __init__(self):
        self._session_bus: Optional[MessageBus] = None
        self._system_bus: Optional[MessageBus] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def _ensure_background_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="dbus-worker")
                self._thread.start()
            return self._loop

    def run_sync(self, coro, timeout: float = 60.0) -> Any:
        loop = self._ensure_background_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    async def get_session_bus(self) -> MessageBus:
        if self._session_bus is None:
            self._session_bus = await MessageBus(bus_type=BusType.SESSION).connect()
        return self._session_bus

    async def get_system_bus(self) -> MessageBus:
        if self._system_bus is None:
            self._system_bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        return self._system_bus

    async def _get_bus(self, bus_type: str = "session") -> MessageBus:
        b_type = str(bus_type).strip().lower()
        if b_type == "system":
            return await self.get_system_bus()
        return await self.get_session_bus()

    @staticmethod
    def _unpack_value(val: Any) -> Any:
        if isinstance(val, Variant):
            return DBusAPI._unpack_value(val.value)
        elif isinstance(val, dict):
            return {str(k): DBusAPI._unpack_value(v) for k, v in val.items()}
        elif isinstance(val, (list, tuple)):
            return [DBusAPI._unpack_value(x) for x in val]
        elif isinstance(val, bytearray):
            return bytes(val).hex()
        return val

    @staticmethod
    def _infer_signature(val: Any) -> str:
        if isinstance(val, bool):
            return "b"
        elif isinstance(val, int):
            return "x" if val.bit_length() > 31 else "i"
        elif isinstance(val, float):
            return "d"
        elif isinstance(val, str):
            return "s"
        elif isinstance(val, list):
            if val and isinstance(val[0], str):
                return "as"
            return "av"
        elif isinstance(val, dict):
            return "a{sv}"
        return "v"

    async def call(
        self,
        bus: str = "session",
        destination: str = "",
        path: str = "",
        interface: str = "",
        member: str = "",
        signature: Optional[str] = None,
        body: Optional[List[Any]] = None,
    ) -> Any:
        msg_bus = await self._get_bus(bus)
        body_args = body or []

        msg_kwargs: Dict[str, Any] = {
            "destination": destination.strip(),
            "path": path.strip(),
            "interface": interface.strip(),
            "member": member.strip(),
            "flags": MessageFlag.ALLOW_INTERACTIVE_AUTHORIZATION if MessageFlag else 0,
        }

        if signature:
            msg_kwargs["signature"] = signature.strip()
            msg_kwargs["body"] = body_args
        elif body_args:
            msg_kwargs["body"] = body_args

        msg = Message(**msg_kwargs)
        reply = await msg_bus.call(msg)

        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"D-Bus Error ({reply.error_name}): {' '.join(str(b) for b in reply.body)}")

        unpacked = [self._unpack_value(x) for x in reply.body]
        if len(unpacked) == 0:
            return "ok"
        elif len(unpacked) == 1:
            return unpacked[0]
        return unpacked

    async def get_property(
        self,
        bus: str = "session",
        destination: str = "",
        path: str = "",
        interface: str = "",
        property_name: Optional[str] = None,
    ) -> Any:
        msg_bus = await self._get_bus(bus)
        if property_name and property_name.strip():
            msg = Message(
                destination=destination.strip(),
                path=path.strip(),
                interface="org.freedesktop.DBus.Properties",
                member="Get",
                signature="ss",
                body=[interface.strip(), property_name.strip()],
                flags=MessageFlag.ALLOW_INTERACTIVE_AUTHORIZATION if MessageFlag else 0,
            )
            reply = await msg_bus.call(msg)
            if reply.message_type == MessageType.ERROR:
                raise RuntimeError(f"D-Bus Error ({reply.error_name}): {' '.join(str(b) for b in reply.body)}")
            return self._unpack_value(reply.body[0]) if reply.body else None
        else:
            msg = Message(
                destination=destination.strip(),
                path=path.strip(),
                interface="org.freedesktop.DBus.Properties",
                member="GetAll",
                signature="s",
                body=[interface.strip()],
                flags=MessageFlag.ALLOW_INTERACTIVE_AUTHORIZATION if MessageFlag else 0,
            )
            reply = await msg_bus.call(msg)
            if reply.message_type == MessageType.ERROR:
                raise RuntimeError(f"D-Bus Error ({reply.error_name}): {' '.join(str(b) for b in reply.body)}")
            return self._unpack_value(reply.body[0]) if reply.body else {}

    async def set_property(
        self,
        bus: str = "session",
        destination: str = "",
        path: str = "",
        interface: str = "",
        property_name: str = "",
        value: Any = None,
        signature: Optional[str] = None,
    ) -> str:
        msg_bus = await self._get_bus(bus)
        val_sig = signature or self._infer_signature(value)
        variant_val = Variant(val_sig, value)

        msg = Message(
            destination=destination.strip(),
            path=path.strip(),
            interface="org.freedesktop.DBus.Properties",
            member="Set",
            signature="ssv",
            body=[interface.strip(), property_name.strip(), variant_val],
            flags=MessageFlag.ALLOW_INTERACTIVE_AUTHORIZATION if MessageFlag else 0,
        )
        reply = await msg_bus.call(msg)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"D-Bus Error ({reply.error_name}): {' '.join(str(b) for b in reply.body)}")
        return f"Property '{property_name}' set successfully on {destination}."

    async def introspect(
        self,
        bus: str = "session",
        destination: str = "",
        path: str = "/",
    ) -> str:
        msg_bus = await self._get_bus(bus)
        msg = Message(
            destination=destination.strip(),
            path=path.strip(),
            interface="org.freedesktop.DBus.Introspectable",
            member="Introspect",
        )
        reply = await msg_bus.call(msg)
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"D-Bus Error ({reply.error_name}): {' '.join(str(b) for b in reply.body)}")
        return reply.body[0] if reply.body else "<node/>"


dbus_api = DBusAPI()


class DBus(BaseYarn):
    name = "dbus_system"
    description = "Universal Dynamic D-Bus Interface for Session and System Bus RPC Calls, Properties, and Introspection."
    version = "2.0.0"
    layer = LAYER_DESKTOP_PROTOCOL  # Layer 50
    dependencies = [
        {"type": "python_module", "target": "dbus_fast"},
        {"type": "env_variable", "target": "DBUS_SESSION_BUS_ADDRESS", "optional": True},
    ]

    def is_available(self) -> bool:
        return bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS") or os.path.exists("/run/dbus/system_bus_socket"))

    @strand(description="Call any D-Bus method on the session or system bus.")
    def dbus_call(
        self,
        destination: str,
        path: str,
        interface: str,
        method: str,
        bus: Literal["session", "system"] = "session",
        signature: Optional[str] = None,
        args: Optional[str] = None,
    ) -> Any:
        """Call any D-Bus method on the session or system bus.

        :param destination: Destination well-known bus name (e.g. 'org.freedesktop.login1').
        :param path: Object path (e.g. '/org/freedesktop/login1').
        :param interface: Interface name (e.g. 'org.freedesktop.login1.Manager').
        :param method: Method member name to invoke (e.g. 'Suspend').
        :param bus: The D-Bus message bus to use ('session' or 'system').
        :param signature: Optional D-Bus signature (e.g. 's', 'b').
        :param args: Optional positional arguments as JSON array string.
        """
        dest = destination.strip()
        p = path.strip()
        iface = interface.strip()
        m = method.strip()
        b = str(bus or "session").strip()

        call_args = []
        if isinstance(args, list):
            call_args = args
        elif isinstance(args, str) and args.strip():
            try:
                parsed = json.loads(args)
                call_args = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                call_args = [args.strip()]

        if not dest or not p or not iface or not m:
            return "Error: destination, path, interface, and method are all required."

        try:
            return dbus_api.run_sync(dbus_api.call(
                bus=b, destination=dest, path=p, interface=iface, member=m, signature=signature, body=call_args
            ))
        except Exception as e:
            return f"Error executing D-Bus call: {e}"

    @strand(description="Get a single property or all properties (GetAll) from a D-Bus object interface.")
    def dbus_get_property(
        self,
        destination: str,
        path: str,
        interface: str,
        bus: Literal["session", "system"] = "session",
        property_name: Optional[str] = None,
    ) -> Any:
        """Get a single property or all properties (GetAll) from a D-Bus object interface.

        :param destination: Destination bus name.
        :param path: Object path.
        :param interface: Interface name.
        :param bus: D-Bus bus name ('session' or 'system').
        :param property_name: Property name (optional, default fetches all).
        """
        dest = destination.strip()
        p = path.strip()
        iface = interface.strip()
        b = str(bus or "session").strip()

        if not dest or not p or not iface:
            return "Error: destination, path, and interface are required."

        try:
            return dbus_api.run_sync(dbus_api.get_property(
                bus=b, destination=dest, path=p, interface=iface, property_name=property_name
            ))
        except Exception as e:
            return f"Error reading D-Bus property: {e}"

    @strand(description="Set a writable D-Bus property on an object interface.")
    def dbus_set_property(
        self,
        destination: str,
        path: str,
        interface: str,
        property_name: str,
        value: str,
        bus: Literal["session", "system"] = "session",
        signature: Optional[str] = None,
    ) -> str:
        """Set a writable D-Bus property on an object interface.

        :param destination: Destination bus name.
        :param path: Object path.
        :param interface: Interface name.
        :param property_name: Writable property name.
        :param value: Value to set.
        :param bus: D-Bus bus name ('session' or 'system').
        :param signature: Optional D-Bus signature.
        """
        dest = destination.strip()
        p = path.strip()
        iface = interface.strip()
        prop = property_name.strip()
        b = str(bus or "session").strip()

        if not dest or not p or not iface or not prop:
            return "Error: destination, path, interface, and property_name are required."

        val: Any = value
        if isinstance(value, str):
            low = value.lower()
            if low in ("true", "1", "yes", "on"):
                val = True
            elif low in ("false", "0", "no", "off"):
                val = False
            elif value.isdigit():
                val = int(value)

        try:
            return dbus_api.run_sync(dbus_api.set_property(
                bus=b, destination=dest, path=p, interface=iface, property_name=prop, value=val, signature=signature
            ))
        except Exception as e:
            return f"Error setting D-Bus property: {e}"

    @strand(description="Introspect a D-Bus node to discover available interfaces, methods, signals, and properties.")
    def dbus_introspect(
        self,
        destination: str,
        bus: Literal["session", "system"] = "session",
        path: str = "/",
    ) -> str:
        """Introspect a D-Bus node to discover available interfaces, methods, signals, and properties.

        :param destination: Destination bus name.
        :param bus: D-Bus bus name ('session' or 'system').
        :param path: Object path.
        """
        dest = destination.strip()
        p = path.strip() if path else "/"
        b = str(bus or "session").strip()

        if not dest:
            return "Error: destination is required."

        try:
            return dbus_api.run_sync(dbus_api.introspect(bus=b, destination=dest, path=p))
        except Exception as e:
            return f"Error introspecting D-Bus node: {e}"
