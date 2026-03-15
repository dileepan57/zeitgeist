"""
Telemetry API router.
Provides monitoring data for the /telemetry dashboard page.
"""
from fastapi import APIRouter, Query
from loguru import logger

from pipeline.telemetry.dashboard import (
    get_collector_health,
    get_recent_runs,
    get_claude_cost_summary,
    get_scoring_metrics,
)

router = APIRouter()


@router.get("")
def get_telemetry_overview(days: int = Query(default=7, ge=1, le=90)):
    """
    Full telemetry overview: collector health, recent runs, Claude cost, scoring metrics.
    """
    return {
        "collector_health": get_collector_health(days=days),
        "recent_runs": get_recent_runs(limit=10),
        "claude_cost": get_claude_cost_summary(days=30),
        "scoring_metrics": get_scoring_metrics(),
    }


@router.get("/collectors")
def get_collectors(days: int = Query(default=7, ge=1, le=90)):
    """
    Per-collector health over last N days.
    Returns list sorted by success_rate ascending (worst-performing first).
    """
    return get_collector_health(days=days)


@router.get("/runs")
def get_runs(limit: int = Query(default=10, ge=1, le=50)):
    """Recent pipeline runs with per-run collector breakdowns."""
    return get_recent_runs(limit=limit)


@router.get("/claude")
def get_claude_usage(days: int = Query(default=30, ge=1, le=365)):
    """
    Claude API usage and cost summary.
    Includes breakdown by call type and daily cost trend.
    """
    return get_claude_cost_summary(days=days)


@router.get("/scoring")
def get_scoring_stats():
    """Scoring distribution metrics: avg/median/p90 opportunity score, timeline distribution."""
    return get_scoring_metrics()
