"""
Textile MCP & LiveKit Compatibility Shims.
Applies monkey-patches for MCP / LiveKit agents compatibility across protocol versions.
"""

import datetime
from typing import Any

import mcp.client.streamable_http
import mcp.types
from mcp.shared import _request_clock

if not hasattr(mcp.client.streamable_http, "GetSessionIdCallback"):
    setattr(mcp.client.streamable_http, "GetSessionIdCallback", None)

if not hasattr(mcp.types.Tool, "inputSchema"):
    setattr(mcp.types.Tool, "inputSchema", property(lambda self: self.input_schema))

if not hasattr(mcp.types.CallToolResult, "isError"):
    setattr(mcp.types.CallToolResult, "isError", property(lambda self: self.is_error))

_orig_request_clock_init = _request_clock.RequestClock.__init__


def _patched_request_clock_init(self: Any, timeout: Any, scope: Any) -> None:
    if isinstance(timeout, datetime.timedelta):
        timeout = timeout.total_seconds()
    _orig_request_clock_init(self, timeout, scope)


_request_clock.RequestClock.__init__ = _patched_request_clock_init
