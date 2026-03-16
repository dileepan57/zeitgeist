"""
Scoring engine instrumentation.
Context manager to time each scoring phase and record metrics.
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


@dataclass
class ScoringPhaseTimer:
    """
    Context manager that records timing for each named phase of the scoring engine.

    Usage:
        timer = ScoringPhaseTimer()
        with timer.phase("independence"):
            result = score_independence(signals)
        with timer.phase("baseline"):
            result = compute_baseline_score(topic, signals)
        timer.log_summary()
    """
    _phases: dict = field(default_factory=dict, init=False, repr=False)
    _current_phase: Optional[str] = field(default=None, init=False, repr=False)
    _current_start: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self):
        self._phases = {}

    class _PhaseContext:
        def __init__(self, timer, name):
            self.timer = timer
            self.name = name

        def __enter__(self):
            self.timer._current_phase = self.name
            self.timer._current_start = time.time()
            return self

        def __exit__(self, *args):
            duration = (time.time() - self.timer._current_start) * 1000
            if self.name not in self.timer._phases:
                self.timer._phases[self.name] = []
            self.timer._phases[self.name].append(duration)
            return False

    def phase(self, name: str) -> "_PhaseContext":
        return self._PhaseContext(self, name)

    def summary(self) -> dict:
        """Return aggregated phase timings."""
        result = {}
        for name, durations in self._phases.items():
            result[name] = {
                "calls": len(durations),
                "total_ms": round(sum(durations), 1),
                "avg_ms": round(sum(durations) / len(durations), 1) if durations else 0,
                "max_ms": round(max(durations), 1) if durations else 0,
            }
        return result

    def total_ms(self) -> float:
        return sum(
            sum(durations)
            for durations in self._phases.values()
        )

    def log_summary(self):
        summary = self.summary()
        total = self.total_ms()
        logger.info(f"Scoring engine phases (total {total:.0f}ms):")
        for phase, metrics in sorted(summary.items(), key=lambda x: x[1]["total_ms"], reverse=True):
            logger.info(f"  {phase}: {metrics['total_ms']:.0f}ms ({metrics['calls']} calls, avg {metrics['avg_ms']:.0f}ms)")
