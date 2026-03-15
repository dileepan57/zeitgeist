"""
Simulator API router.
Exposes scenario listing, on-demand simulation runs, and history.
"""
import threading
from datetime import date
from fastapi import APIRouter, BackgroundTasks, HTTPException
from loguru import logger

from simulator.scenarios import SCENARIOS, get_all_scenarios
from simulator.reporter import generate_report

router = APIRouter()

# Cache the last run result in memory (simple, no DB needed for UI)
_last_run: dict | None = None
_running = False


@router.get("/scenarios")
def list_scenarios():
    """List all available simulation scenarios with descriptions."""
    return [
        {
            "name": s["name"],
            "description": s.get("description", ""),
            "signal_count": len(s.get("signals", [])),
        }
        for s in get_all_scenarios()
    ]


@router.post("/run")
def run_all_scenarios(background_tasks: BackgroundTasks):
    """
    Run all 10 scenarios and return results.
    Also stores results to DB in background.
    """
    global _running
    if _running:
        return {"status": "already_running", "message": "A simulation is already in progress"}

    from simulator.runner import run_all, persist_results
    results = run_all()

    background_tasks.add_task(persist_results, results)

    global _last_run
    _last_run = results

    return results


@router.post("/run/{scenario_name}")
def run_single_scenario(scenario_name: str):
    """Run a single named scenario and return the result."""
    if scenario_name not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_name}' not found")

    from simulator.runner import run_scenario
    return run_scenario(scenario_name)


@router.get("/report")
def get_last_report():
    """
    Return the latest simulation report as markdown.
    Run /simulator/run first to generate a report.
    """
    if _last_run is None:
        return {"report": None, "message": "No simulation has been run yet. POST /api/simulator/run first."}
    return {"report": generate_report(_last_run), "summary": _last_run}


@router.get("/history")
def get_simulation_history(limit: int = 30):
    """Retrieve past simulation run results from the DB."""
    try:
        from pipeline.utils.db import get_client
        client = get_client()
        rows = (
            client.table("simulation_runs")
            .select("*")
            .order("run_date", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return rows
    except Exception as e:
        logger.warning(f"Simulator history: {e}")
        return []


@router.get("/summary")
def get_simulator_summary():
    """Per-scenario pass rate from historical runs."""
    try:
        from pipeline.utils.db import get_client
        client = get_client()
        rows = client.table("simulator_summary").select("*").execute().data
        return rows
    except Exception as e:
        logger.warning(f"Simulator summary: {e}")
        return []
