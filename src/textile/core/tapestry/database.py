"""
Textile Telemetry Database Management.
Provides SQLite WAL persistent and memory-backed database connection management.
"""

import contextlib
import os
import sqlite3
import tempfile
import threading
from collections.abc import Generator
from pathlib import Path


def _get_runtime_directory() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    directory = Path(runtime_dir) / "textile" if runtime_dir else Path(tempfile.gettempdir()) / f"textile-{os.getuid()}"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(directory, 0o700)
    return directory


class TapestryDatabase:
    """Unified SQLite WAL storage manager for Task Ledger and Sensory Blackboard."""

    def __init__(self, persist: bool = True):
        if persist:
            self._database_path = str(_get_runtime_directory() / "tapestry.db")
            self._is_uri = False
        else:
            self._database_path = f"file:memdb_{id(self)}?mode=memory&cache=shared"
            self._is_uri = True
        self._lock = threading.RLock()
        self._local_storage = threading.local()
        self._initialize_database()

    def get_connection(self) -> sqlite3.Connection:
        connection = getattr(self._local_storage, "connection", None)
        if connection is None:
            connection = sqlite3.connect(
                self._database_path,
                timeout=15.0,
                uri=self._is_uri,
                autocommit=True,
            )
            connection.execute("PRAGMA busy_timeout=15000;")
            if not self._is_uri:
                connection.execute("PRAGMA journal_mode=WAL;")
                connection.execute("PRAGMA synchronous=NORMAL;")
            self._local_storage.connection = connection
        return connection

    @contextlib.contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Provide a thread-safe connection context for transactions."""
        with self._lock, self.get_connection() as connection:
            yield connection

    def _initialize_database(self) -> None:
        with self._lock, self.get_connection() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS active_tasks (
                    task_id TEXT PRIMARY KEY,
                    strand_name TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    args_json TEXT,
                    tier TEXT
                );
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    strand_name TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    duration_ms REAL,
                    success INTEGER,
                    error TEXT,
                    tier TEXT,
                    args_json TEXT
                );
                CREATE TABLE IF NOT EXISTS slots (
                    key TEXT PRIMARY KEY,
                    val_json TEXT
                );
                CREATE TABLE IF NOT EXISTS notices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    message TEXT NOT NULL,
                    data_json TEXT
                );
            """)
        if not self._is_uri and Path(self._database_path).exists():
            with contextlib.suppress(OSError):
                os.chmod(self._database_path, 0o600)


class _DatabaseState:
    default: TapestryDatabase | None = None


def get_default_database(persist: bool = True) -> TapestryDatabase:
    """Retrieve shared TapestryDatabase instance for persistent storage."""
    if persist:
        if _DatabaseState.default is None:
            _DatabaseState.default = TapestryDatabase(persist=True)
        return _DatabaseState.default
    return TapestryDatabase(persist=False)
