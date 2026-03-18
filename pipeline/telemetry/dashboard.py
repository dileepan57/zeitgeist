"""
Telemetry dashboard aggregation helpers.
Used by api/routers/telemetry.py to build the monitoring view.
"""
from datetime import date, timedelta
from typing import Optional
from loguru import logger


def get_collector_health(days: int = 7) -> list[dict]:
    """
    Per-collector health over the last N days.
    Returns list sorted by success_rate ascending (worst first).
    """
    try:
        from pipeline.utils.db import get_client
        client = get_client()
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        rows = (
            client.table("collector_runs")
            .select("*")
            .gte("created_at", cutoff)
            .execute()
            .data
        )

        # Aggregate per collector
        by_collector: dict[str, dict] = {}
        for row in rows:
            name = row["collector_name"]
            if name not in by_collector:
                by_collector[name] = {
                    "collector_name": name,
                    "total_runs": 0,
                    "successes": 0,
                    "failures": 0,
                    "blocked": 0,
                    "total_items": 0,
                    "total_duration_ms": 0,
                    "last_run": None,
                    "last_status": None,
                    "last_error": None,
                }
            stats = by_collector[name]
            stats["total_runs"] += 1
            if row["status"] == "success":
                stats["successes"] += 1
            elif row["status"] in ("error",):
                stats["failures"] += 1
            elif row["status"] == "blocked":
                stats["blocked"] += 1
            stats["total_items"] += row.get("items_collected") or 0
            stats["total_duration_ms"] += row.get("duration_ms") or 0
            if stats["last_run"] is None or row["created_at"] > stats["last_run"]:
                stats["last_run"] = row["created_at"]
                stats["last_status"] = row["status"]
                stats["last_error"] = row.get("error_msg")

        result = []
        for stats in by_collector.values():
            n = stats["total_runs"]
            stats["success_rate_pct"] = round(100.0 * stats["successes"] / n, 1) if n else 0
            stats["avg_duration_ms"] = round(stats["total_duration_ms"] / n) if n else 0
            stats["avg_items"] = round(stats["total_items"] / n, 1) if n else 0
            # Health: green=success, yellow=blocked/partial, red=error
            if stats["last_status"] == "success":
                stats["health"] = "green"
            elif stats["last_status"] in ("blocked", "partial"):
                stats["health"] = "yellow"
            else:
                stats["health"] = "red"
            result.append(stats)

        return sorted(result, key=lambda x: x["success_rate_pct"])

    except Exception as e:
        logger.warning(f"Telemetry: get_collector_health failed: {e}")
        return []


def get_recent_runs(limit: int = 10) -> list[dict]:
    """Recent pipeline runs with per-run collector stats."""
    try:
        from pipeline.utils.db import get_client
        client = get_client()

        runs = (
            client.table("daily_runs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )

        for run in runs:
            run_id = run["id"]
            collectors = (
                client.table("collector_runs")
                .select("collector_name, status, duration_ms, items_collected")
                .eq("run_id", run_id)
                .execute()
                .data
            )
            run["collectors"] = collectors
            run["total_collectors"] = len(collectors)
            run["collector_successes"] = sum(1 for c in collectors if c["status"] == "success")
            run["total_duration_ms"] = sum(c.get("duration_ms") or 0 for c in collectors)

        return runs
    except Exception as e:
        logger.warning(f"Telemetry: get_recent_runs failed: {e}")
        return []


def get_claude_cost_summary(days: int = 30) -> dict:
    """Aggregate Claude API cost and usage stats."""
    try:
        from pipeline.utils.db import get_client
        client = get_client()
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        rows = (
            client.table("claude_usage")
            .select("*")
            .gte("created_at", cutoff)
            .execute()
            .data
        )

        total_cost = sum(r.get("cost_usd") or 0 for r in rows)
        total_tokens = sum(r.get("total_tokens") or 0 for r in rows)
        total_calls = len(rows)
        errors = sum(1 for r in rows if not r.get("success", True))

        by_type: dict[str, dict] = {}
        for row in rows:
            ct = row.get("call_type", "unknown")
            if ct not in by_type:
                by_type[ct] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
            by_type[ct]["calls"] += 1
            by_type[ct]["tokens"] += row.get("total_tokens") or 0
            by_type[ct]["cost_usd"] += row.get("cost_usd") or 0

        # Daily cost breakdown
        daily: dict[str, float] = {}
        for row in rows:
            day = row["created_at"][:10]
            daily[day] = daily.get(day, 0) + (row.get("cost_usd") or 0)

        return {
            "period_days": days,
            "total_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "total_calls": total_calls,
            "error_calls": errors,
            "by_call_type": by_type,
            "daily_cost": [
                {"date": d, "cost_usd": round(c, 4)}
                for d, c in sorted(daily.items())
            ],
        }
    except Exception as e:
        logger.warning(f"Telemetry: get_claude_cost_summary failed: {e}")
        return {}


def get_scoring_metrics(limit: int = 30) -> dict:
    """Recent scoring distribution stats from topic_scores."""
    try:
        from pipeline.utils.db import get_client
        client = get_client()

        rows = (
            client.table("topic_scores")
            .select("opportunity_score, independence_score, timeline_position")
            .order("created_at", desc=True)
            .limit(500)
            .execute()
            .data
        )

        if not rows:
            return {}

        scores = [r["opportunity_score"] for r in rows if r.get("opportunity_score") is not None]
        timeline_counts: dict[str, int] = {}
        for r in rows:
            pos = r.get("timeline_position") or "UNKNOWN"
            timeline_counts[pos] = timeline_counts.get(pos, 0) + 1

        return {
            "sample_size": len(scores),
            "avg_opportunity_score": round(sum(scores) / len(scores), 4) if scores else 0,
            "median_opportunity_score": round(sorted(scores)[len(scores) // 2], 4) if scores else 0,
            "p90_opportunity_score": round(sorted(scores)[int(len(scores) * 0.9)], 4) if scores else 0,
            "timeline_distribution": timeline_counts,
        }
    except Exception as e:
        logger.warning(f"Telemetry: get_scoring_metrics failed: {e}")
        return {}
