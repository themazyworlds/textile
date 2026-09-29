"""
Systemd Journal & Kernel Log Stream Capability Yarn for Textile.
Provides structured system log querying, crash diagnosis, service logs, and kernel message inspection.
Layer 50 (Desktop Protocol).
"""

import datetime
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

from textile import Yarn, strand


@dataclass
class JournalQueryParams:
    unit: str | None = None
    user_unit: str | None = None
    priority: str | None = None
    since: str | None = "-1h"
    until: str | None = None
    lines: int = 25
    kernel: bool = False
    grep: str | None = None
    boot: int | None = None
    user: bool = False

PRIORITY_NAMES = {
    0: "emerg",
    1: "alert",
    2: "crit",
    3: "err",
    4: "warning",
    5: "notice",
    6: "info",
    7: "debug",
}

OUTPUT_FIELDS = "__REALTIME_TIMESTAMP,PRIORITY,_SYSTEMD_USER_UNIT,_SYSTEMD_UNIT,SYSLOG_IDENTIFIER,_COMM,_PID,MESSAGE"


def _normalize_time_spec(spec: str | None) -> str | None:
    if not spec:
        return None
    s = str(spec).strip()
    if not s:
        return None
    if s.startswith("-") or s.lower() in ("today", "yesterday", "now"):
        return s
    if re.match(r"^\d+[smhdw]$", s, re.IGNORECASE):
        return f"-{s}"
    match = re.match(r"^(\d+)\s*(sec|min|hour|day|week)s?\s*ago$", s, re.IGNORECASE)
    if match:
        num, unit = match.group(1), match.group(2).lower()
        unit_map = {"sec": "s", "min": "m", "hour": "h", "day": "d", "week": "w"}
        return f"-{num}{unit_map.get(unit, 'm')}"
    return s


def _parse_entry(obj: dict[str, Any], is_kernel: bool = False) -> dict[str, Any]:
    """Safely parse a single journalctl JSON line object."""
    ts_us = int(obj.get("__REALTIME_TIMESTAMP", 0)) if str(obj.get("__REALTIME_TIMESTAMP", "")).isdigit() else 0
    ts_str = ""
    if ts_us:
        try:
            ts_str = datetime.datetime.fromtimestamp(ts_us / 1_000_000).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError, OverflowError, OSError):
            ts_str = str(ts_us)

    prio_raw = obj.get("PRIORITY", 6)
    prio_val = int(prio_raw) if str(prio_raw).isdigit() else 6
    prio_name = PRIORITY_NAMES.get(prio_val, str(prio_val))

    unit_name = (
        obj.get("_SYSTEMD_USER_UNIT")
        or obj.get("_SYSTEMD_UNIT")
        or obj.get("SYSLOG_IDENTIFIER")
        or obj.get("_COMM")
        or ("kernel" if is_kernel else "system")
    )

    raw_msg = obj.get("MESSAGE", "")
    if isinstance(raw_msg, list):
        try:
            msg = bytes(raw_msg).decode("utf-8", errors="replace").strip()
        except (UnicodeDecodeError, TypeError, ValueError, AttributeError):
            msg = str(raw_msg)
    else:
        msg = str(raw_msg).strip()

    return {
        "timestamp": ts_str,
        "unit": unit_name,
        "priority": prio_name,
        "pid": obj.get("_PID"),
        "message": msg,
    }


class JournalAPI:
    """Systemd Journal Query & Diagnostic Engine."""

    def __init__(self):
        self._journalctl_bin: str | None = shutil.which("journalctl")

    def is_available(self) -> bool:
        if not self._journalctl_bin:
            return False
        return os.path.exists("/run/systemd/journal") or os.path.exists("/var/log/journal")

    def _exec_journal(self, cmd: list[str]) -> list[dict[str, Any]]:
        """Run journalctl command and return parsed log records."""
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=10, check=False)
            if res.returncode != 0 and not res.stdout:
                err = res.stderr.strip()
                return [{"error": f"journalctl error ({res.returncode}): {err}"}]

            parsed = []
            is_kernel = "-k" in cmd
            for line in res.stdout.splitlines():
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    obj = json.loads(line_str)
                    parsed.append(_parse_entry(obj, is_kernel=is_kernel))
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

            return parsed
        except subprocess.TimeoutExpired:
            return [{"error": "journalctl query timed out."}]
        except (OSError, subprocess.SubprocessError) as e:
            return [{"error": f"Error executing journalctl: {e}"}]

    def _build_journalctl_cmd(self, p: JournalQueryParams) -> list[str]:
        base_cmd = [
            self._journalctl_bin,
            "-o",
            "json",
            "--no-pager",
            f"--output-fields={OUTPUT_FIELDS}",
        ]
        limit = max(1, min(int(p.lines or 25), 200))
        base_cmd.extend(["-n", str(limit)])

        if p.boot is not None:
            base_cmd.extend(["-b", str(p.boot)])
        if p.kernel:
            base_cmd.append("-k")
        if p.user:
            base_cmd.append("--user")
        if p.user_unit:
            base_cmd.extend(["--user-unit", str(p.user_unit)])
        if p.priority:
            base_cmd.extend(["-p", str(p.priority)])

        norm_since = _normalize_time_spec(p.since)
        if norm_since:
            base_cmd.extend(["--since", norm_since])

        norm_until = _normalize_time_spec(p.until)
        if norm_until:
            base_cmd.extend(["--until", norm_until])

        if p.grep:
            base_cmd.extend(["-g", str(p.grep)])
        return base_cmd

    def query_logs(
        self,
        query: JournalQueryParams | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        if not self.is_available():
            return [{"error": "systemd journalctl is not available."}]

        p = query or JournalQueryParams(**kwargs)
        base_cmd = self._build_journalctl_cmd(p)

        if p.unit and not p.user_unit:
            cmd_system = list(base_cmd)
            cmd_system.extend(["-u", str(p.unit)])
            results = self._exec_journal(cmd_system)

            if not results or (len(results) == 1 and "error" in results[0]):
                cmd_user = list(base_cmd)
                cmd_user.extend(["--user-unit", str(p.unit)])
                user_results = self._exec_journal(cmd_user)
                if user_results and not (len(user_results) == 1 and "error" in user_results[0]):
                    return user_results
            return results

        if p.unit and p.user_unit:
            base_cmd.extend(["-u", str(p.unit)])

        return self._exec_journal(base_cmd)

    def get_errors(self, since: str = "-1h", lines: int = 25) -> list[dict[str, Any]]:
        return self.query_logs(priority="err", since=since, lines=lines, boot=0)

    def get_kernel_logs(self, since: str = "-1h", lines: int = 25) -> list[dict[str, Any]]:
        return self.query_logs(kernel=True, since=since, lines=lines, boot=0)


journal_api = JournalAPI()


class Journal(Yarn):
    def is_available(self) -> bool:
        return journal_api.is_available()

    @strand(tier="observe")
    def journal_query(
        self,
        query: JournalQueryParams | None = None,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Query systemd journal logs with structured filtering by unit, priority, time range, or grep."""
        return journal_api.query_logs(query=query, **kwargs)

    @strand(tier="observe")
    def journal_get_errors(self, since: str = "-1h", lines: int = 25) -> list[dict[str, Any]]:
        """Fast diagnostic tool to retrieve recent system and user error logs.

        :param since: Time window (default '-1h').
        :param lines: Max error entries (default 25).
        """
        return journal_api.get_errors(since=since, lines=lines)

    @strand(tier="observe")
    def journal_get_kernel(self, since: str = "-1h", lines: int = 25) -> list[dict[str, Any]]:
        """Retrieve recent kernel hardware, driver, ACPI, GPU, and dmesg log entries.

        :param since: Time window (default '-1h').
        :param lines: Max entries (default 25).
        """
        return journal_api.get_kernel_logs(since=since, lines=lines)
