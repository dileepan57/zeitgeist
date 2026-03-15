"""
Evals API router.
GET  /api/evals              — latest eval results per type
GET  /api/evals/history      — all eval results over time (with optional date filter)
POST /api/evals/run          — trigger eval run (background, returns immediately)
"""
import threading
from datetime import date
from fastapi import APIRouter, BackgroundTasks, Query
from loguru import logger

router = APIRouter()

# In-memory state for background run
_running = False
_last_run_results: list[dict] = []


def _run_evals_background(include_claude: bool):
    global _running, _last_run_results
    try:
        from evals.runner import run_all, persist_results
        results = run_all(include_claude=include_claude)
        _last_run_results = results
        persist_results(results)
        passed = sum(1 for r in results if r.get("passed"))
        logger.info(f"Background eval run complete: {passed}/{len(results)} passed")
    except Exception as e:
        logger.error(f"Background eval run failed: {e}")
    finally:
        _running = False


@router.get("")
def get_latest_evals():
    """Return latest eval result per eval type from DB."""
    try:
        from pipeline.utils.db import get_client
        client = get_client()
        # Use the latest_evals view
        rows = client.table("latest_evals").select("*").execute().data or []
        return {
            "evals": rows,
            "total": len(rows),
            "passed": sum(1 for r in rows if r.get("passed")),
            "failed": sum(1 for r in rows if not r.get("passed") and r.get("metric_value") is not None),
        }
    except Exception as e:
        logger.warning(f"Evals fetch error: {e}")
        return {"evals": [], "total": 0, "passed": 0, "failed": 0, "error": str(e)}


@router.get("/history")
def get_eval_history(
    eval_name: str | None = Query(None, description="Filter by eval name"),
    days: int = Query(30, description="Look back N days"),
):
    """Return all eval results over time, optionally filtered by eval name."""
    try:
        from pipeline.utils.db import get_client
        client = get_client()
        query = client.table("eval_results").select("*").order("run_date", desc=True)
        if eval_name:
            query = query.eq("eval_name", eval_name)
        rows = query.execute().data or []
        return {
            "results": rows,
            "total": len(rows),
            "eval_name": eval_name,
        }
    except Exception as e:
        logger.warning(f"Eval history fetch error: {e}")
        return {"results": [], "total": 0, "error": str(e)}


@router.post("/run")
def trigger_eval_run(
    background_tasks: BackgroundTasks,
    include_claude: bool = Query(False, description="Include Claude-dependent evals (costs ~$0.10)"),
):
    """Trigger a background eval run. Returns immediately."""
    global _running
    if _running:
        return {"status": "already_running", "message": "An eval run is already in progress"}

    _running = True
    background_tasks.add_task(_run_evals_background, include_claude)

    return {
        "status": "started",
        "include_claude": include_claude,
        "message": f"Eval run started in background. {'Includes' if include_claude else 'Excludes'} Claude-dependent evals.",
    }


@router.get("/run/status")
def get_run_status():
    """Check if an eval run is currently in progress."""
    return {
        "running": _running,
        "last_run_count": len(_last_run_results),
        "last_run_passed": sum(1 for r in _last_run_results if r.get("passed")) if _last_run_results else None,
        "last_run_results": _last_run_results if not _running else [],
    }
