"""
Telemetry storage — writes events to the DB.
All functions are best-effort: they log warnings on failure but never raise.
"""
from typing import Optional
from loguru import logger


def flush_collector_run(
    run_id: Optional[str],
    collector_name: str,
    status: str,
    items_collected: int,
    duration_ms: int,
    error_msg: Optional[str] = None,
) -> None:
    """Write a collector run record to the collector_runs table."""
    if run_id == "dry-run":
        return
    try:
        from pipeline.utils.db import get_client
        client = get_client()
        client.table("collector_runs").insert({
            "run_id": run_id,
            "collector_name": collector_name,
            "status": status,
            "items_collected": items_collected,
            "duration_ms": duration_ms,
            "error_msg": error_msg,
        }).execute()
    except Exception as e:
        # Telemetry must never crash the pipeline
        logger.debug(f"Telemetry: failed to store collector run for '{collector_name}': {e}")


def flush_claude_usage(
    run_id: Optional[str],
    call_type: str,
    topic: Optional[str],
    input_tokens: int,
    output_tokens: int,
    duration_ms: int,
    success: bool = True,
    error_msg: Optional[str] = None,
) -> None:
    """
    Write a Claude API call record to the claude_usage table.
    Cost estimated at Sonnet pricing: $3/1M input, $15/1M output tokens.
    """
    if run_id == "dry-run":
        return
    try:
        total_tokens = input_tokens + output_tokens
        # claude-sonnet-4-6 pricing (as of 2025): $3/M input, $15/M output
        cost_usd = (input_tokens / 1_000_000 * 3.0) + (output_tokens / 1_000_000 * 15.0)

        from pipeline.utils.db import get_client
        client = get_client()
        client.table("claude_usage").insert({
            "run_id": run_id,
            "call_type": call_type,
            "topic": topic,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "duration_ms": duration_ms,
            "cost_usd": round(cost_usd, 6),
            "success": success,
            "error_msg": error_msg,
        }).execute()
    except Exception as e:
        logger.debug(f"Telemetry: failed to store Claude usage: {e}")


def snapshot_signal_performance() -> None:
    """
    Copy current signal_performance rows into signal_perf_history.
    Called at the end of each weekly calibration run.
    """
    try:
        from pipeline.utils.db import get_client
        from datetime import date
        client = get_client()

        current = client.table("signal_performance").select("*").execute().data
        if not current:
            return

        today = date.today().isoformat()
        rows = []
        for row in current:
            rows.append({
                "signal_source": row["signal_source"],
                "precision": row.get("precision"),
                "recall": row.get("recall"),
                "true_positives": row.get("true_positives", 0),
                "false_positives": row.get("false_positives", 0),
                "true_negatives": row.get("true_negatives", 0),
                "false_negatives": row.get("false_negatives", 0),
                "snapshot_date": today,
            })

        client.table("signal_perf_history").insert(rows).execute()
        logger.info(f"Telemetry: snapshotted {len(rows)} signal performance rows")
    except Exception as e:
        logger.warning(f"Telemetry: failed to snapshot signal performance: {e}")
