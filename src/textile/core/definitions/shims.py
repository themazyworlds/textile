"""
Textile MCP & LiveKit Compatibility Shims.
Applies monkey-patches for MCP / LiveKit agents compatibility across protocol versions.
"""

import contextlib
import datetime
from typing import Any

with contextlib.suppress(ImportError, AttributeError):
    from mcp.shared import _request_clock

    _orig_request_clock_init = _request_clock.RequestClock.__init__

    def _patched_request_clock_init(self: Any, timeout: Any, scope: Any) -> None:
        if isinstance(timeout, datetime.timedelta):
            timeout = timeout.total_seconds()
        _orig_request_clock_init(self, timeout, scope)

    _request_clock.RequestClock.__init__ = _patched_request_clock_init
