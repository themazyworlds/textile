"""
Textile Seams - Circuit Breaker & Runtime Execution Failure Sentinel.
"""

from textile.core.telemetry.log import get_logger

logger = get_logger(__name__)

__all__ = ["SeamOrchestrator", "seams"]


class SeamOrchestrator:
    """Runtime execution failure & circuit breaker sentinel."""

    def __init__(self, max_consecutive_failures: int = 3):
        self._failure_counts: dict[str, int] = {}
        self._max_consecutive_failures = max_consecutive_failures

    def record_strand_execution(self, strand_name: str, success: bool, error: str | None = None) -> None:
        """Record strand execution success or failure for circuit breaker monitoring."""
        if success:
            self._failure_counts[strand_name] = 0
            return

        cnt = self._failure_counts.get(strand_name, 0) + 1
        self._failure_counts[strand_name] = cnt
        logger.warning(
            "seams.strand_failed",
            strand=strand_name,
            failures=cnt,
            max_failures=self._max_consecutive_failures,
            error=error,
        )

        if cnt >= self._max_consecutive_failures:
            logger.error(
                "seams.circuit_breaker_tripped",
                strand=strand_name,
                failures=cnt,
                max_failures=self._max_consecutive_failures,
            )


seams = SeamOrchestrator()
