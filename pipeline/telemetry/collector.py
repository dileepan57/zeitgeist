"""
Collector instrumentation.
Wraps each collector's collect() call with timing, success tracking, and item counting.

Usage:
    from pipeline.telemetry import instrument_collector

    # Option A: decorator (used in run.py when calling each collector)
    results = instrument_collector("wikipedia", run_id=run_id)(wikipedia.collect)()

    # Option B: context manager
    with CollectorTelemetry("wikipedia", run_id=run_id) as ct:
        results = wikipedia.collect()
        ct.set_items(len(results))
"""
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Optional
from loguru import logger

from pipeline.telemetry.store import flush_collector_run


@dataclass
class CollectorTelemetry:
    collector_name: str
    run_id: Optional[str] = None
    _start: float = field(default=0.0, init=False, repr=False)
    _items: int = field(default=0, init=False, repr=False)
    _status: str = field(default="success", init=False, repr=False)
    _error: Optional[str] = field(default=None, init=False, repr=False)

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self._start) * 1000)
        if exc_type is not None:
            self._status = "error"
            self._error = f"{exc_type.__name__}: {exc_val}"
        flush_collector_run(
            run_id=self.run_id,
            collector_name=self.collector_name,
            status=self._status,
            items_collected=self._items,
            duration_ms=duration_ms,
            error_msg=self._error,
        )
        # Don't suppress exceptions
        return False

    def set_items(self, count: int):
        self._items = count

    def set_blocked(self):
        self._status = "blocked"

    def set_partial(self, items: int):
        self._status = "partial"
        self._items = items


def instrument_collector(collector_name: str, run_id: Optional[str] = None):
    """
    Decorator factory. Wraps a collect() function with telemetry.

    Usage in run.py:
        from pipeline.telemetry import instrument_collector
        results = instrument_collector("wikipedia", run_id)(wikipedia.collect)()
    """
    def decorator(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            start = time.time()
            status = "success"
            error_msg = None
            results = []
            try:
                results = fn(*args, **kwargs)
                if results is None:
                    results = []
                # Infer blocked status from zero results (best-effort)
                if len(results) == 0:
                    status = "blocked"
            except Exception as e:
                status = "error"
                error_msg = f"{type(e).__name__}: {e}"
                logger.warning(f"Collector '{collector_name}' error: {error_msg}")
                results = []
            finally:
                duration_ms = int((time.time() - start) * 1000)
                flush_collector_run(
                    run_id=run_id,
                    collector_name=collector_name,
                    status=status,
                    items_collected=len(results) if results else 0,
                    duration_ms=duration_ms,
                    error_msg=error_msg,
                )
            return results
        return wrapper
    return decorator
