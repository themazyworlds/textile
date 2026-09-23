"""
Textile Core Layer 4 - Reversible Transactional Execution & Undo Engine.
Maintains execution history stack and handles state rollbacks for undoable strands.
"""

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from textile.core.base import STRAND_EXEC_ERRORS

logger = logging.getLogger(__name__)


@dataclass
class Transaction:
    """Represents a completed strand execution transaction with an optional rollback handler."""

    strand_name: str
    parameters: dict[str, Any]
    transaction_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rollback_handler: Callable[[], Any] | None = None
    pre_state: dict[str, Any] = field(default_factory=dict)
    result_data: Any = None


class TransactionStack:
    """Thread-safe transactional history stack for rolling back executed strands."""

    def __init__(self, max_history: int = 50):
        self._lock = threading.RLock()
        self._stack: list[Transaction] = []
        self._max_history = max_history

    def push(self, transaction: Transaction) -> None:
        with self._lock:
            self._stack.append(transaction)
            if len(self._stack) > self._max_history:
                self._stack.pop(0)

    def undo_last(self) -> tuple[bool, str]:
        with self._lock:
            if not self._stack:
                return False, "No transactions available to undo."

            tx = self._stack.pop()
            if tx.rollback_handler is not None:
                try:
                    tx.rollback_handler()
                    return True, f"Successfully rolled back transaction for strand '{tx.strand_name}'."
                except STRAND_EXEC_ERRORS as e:
                    logger.error(f"Rollback failed for transaction '{tx.transaction_id}': {e}")
                    return False, f"Rollback failed for strand '{tx.strand_name}': {e}"
            return True, f"Undid transaction for strand '{tx.strand_name}' (no state mutation occurred)."

    def clear(self) -> None:
        with self._lock:
            self._stack.clear()


transaction_stack = TransactionStack()
