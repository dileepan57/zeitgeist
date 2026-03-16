"""
Telemetry and sensor framework for Zeitgeist.
Instruments every layer of the system: collectors, scoring, synthesis, and the pipeline overall.
"""
from pipeline.telemetry.collector import instrument_collector, CollectorTelemetry
from pipeline.telemetry.scoring import ScoringPhaseTimer
from pipeline.telemetry.store import flush_collector_run, flush_claude_usage

__all__ = [
    "instrument_collector",
    "CollectorTelemetry",
    "ScoringPhaseTimer",
    "flush_collector_run",
    "flush_claude_usage",
]
