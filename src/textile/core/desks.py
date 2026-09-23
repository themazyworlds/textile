"""
Textile Tier Capability Passes & Desks (Object Capabilities).

Implements the "Room Pass" architecture:
- ObserverDesk: Read-only desk. Destructive or mutating methods do not even exist on this object.
- InteractDesk: UI and sensory interaction desk.
- MutateDesk: Workspace mutation desk, bounded by ScopedPath and tracked in TransactionStack.
- PrivilegedDesk: System configuration and high-trust operations.
"""

from pathlib import Path
from typing import Any

from textile.core.guardrails import ScopedPath
from textile.core.transaction import Transaction, transaction_stack


class ObserverDesk:
    """
    Object Capability Desk for OBSERVE tier strands.
    Physically possesses only read/query methods.
    Write, remove, delete, and execute methods do not exist on this object.
    """

    def __init__(self, root: str | Path | None = None):
        self._scoped = ScopedPath(root=root)

    @property
    def root(self) -> Path:
        return self._scoped.root

    def read_text(self, path: str | Path, encoding: str = "utf-8") -> str:
        target = self._scoped.resolve(path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")
        return target.read_text(encoding=encoding, errors="replace")

    def read_bytes(self, path: str | Path) -> bytes:
        target = self._scoped.resolve(path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {target}")
        return target.read_bytes()

    def list_dir(self, path: str | Path = ".") -> list[str]:
        target = self._scoped.resolve(path)
        if not target.exists() or not target.is_dir():
            raise NotADirectoryError(f"Directory not found: {target}")
        return [entry.name for entry in target.iterdir()]

    def stat(self, path: str | Path) -> dict[str, Any]:
        target = self._scoped.resolve(path)
        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target}")
        st = target.stat()
        return {
            "size_bytes": st.st_size,
            "is_dir": target.is_dir(),
            "mtime": st.st_mtime,
            "mode": oct(st.st_mode),
        }


class InteractDesk(ObserverDesk):
    """
    Object Capability Desk for INTERACT tier strands.
    Inherits read capabilities from ObserverDesk and adds desktop/UI interaction capabilities.
    """

    def __init__(self, root: str | Path | None = None):
        super().__init__(root=root)

    def notify(self, message: str, title: str = "Textile") -> str:
        return f"Notification [{title}]: {message}"


class MutateDesk(InteractDesk):
    """
    Object Capability Desk for MUTATE tier strands.
    Possesses write and modification capabilities, strictly bounded by ScopedPath
    and registered on the Layer 4 TransactionStack for instant rollback.
    """

    def __init__(self, root: str | Path | None = None):
        super().__init__(root=root)

    def write_text(self, path: str | Path, content: str, encoding: str = "utf-8") -> Path:
        target = self._scoped.resolve(path)
        old_content = target.read_text(encoding=encoding, errors="replace") if target.exists() else None

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)

        # Register rollback handler on transaction stack
        def _rollback():
            if old_content is not None:
                target.write_text(old_content, encoding=encoding)
            elif target.exists():
                target.unlink()

        transaction_stack.push(
            Transaction(
                strand_name="desk_write_text",
                parameters={"path": str(target)},
                rollback_handler=_rollback,
            )
        )
        return target

    def create_dir(self, path: str | Path) -> Path:
        target = self._scoped.resolve(path)
        target.mkdir(parents=True, exist_ok=True)
        return target


class PrivilegedDesk(MutateDesk):
    """
    Object Capability Desk for PRIVILEGED tier strands.
    Requires verified high-trust local seat authentication.
    """
    pass
