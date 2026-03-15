"""
Eval 5: App Fit Calibration
For apps that have been built + have RevenueCat data:
  - Compare original app_fit_score with actual retention/revenue outcome
  - Track Pearson correlation coefficient over time

Initially runs with empty data and accumulates as apps ship.
No Claude API calls needed — purely computes against historical app outcomes.
"""
from loguru import logger

CORRELATION_THRESHOLD = 0.5  # Acceptable correlation once we have >= 5 data points
MIN_SAMPLE_SIZE = 5  # Don't compute correlation with fewer points


def run_app_fit_eval() -> dict:
    """
    Compute correlation between predicted app_fit_score and actual app outcomes.
    Returns app fit calibration eval result.
    """
    try:
        from pipeline.utils.db import get_client
        client = get_client()

        # Fetch app projects that have revenue data
        apps = client.table("app_projects").select("*").execute().data or []
        if not apps:
            return _no_data_result("No app projects yet. Will accumulate as apps are built and launched.")

        # Fetch revenue data for launched apps
        revenue_rows = client.table("app_revenue").select("*").execute().data or []
        revenue_by_project = {}
        for row in revenue_rows:
            pid = row.get("project_id")
            if pid not in revenue_by_project:
                revenue_by_project[pid] = []
            revenue_by_project[pid].append(row)

        # Fetch topic syntheses for app_fit_score
        syntheses = client.table("topic_syntheses").select("*").execute().data or []
        fit_score_by_topic = {s.get("topic_id"): s.get("app_fit_score") for s in syntheses if s.get("app_fit_score") is not None}

        # Build pairs: (predicted_fit_score, actual_outcome_score)
        pairs = []
        for app in apps:
            topic_id = app.get("opportunity_topic_id")
            project_id = app.get("id")
            predicted_fit = fit_score_by_topic.get(topic_id)
            if predicted_fit is None:
                continue

            app_revenue = revenue_by_project.get(project_id, [])
            if not app_revenue:
                continue

            # Compute actual outcome: normalized MRR / retention proxy
            latest_revenue = max(app_revenue, key=lambda r: r.get("date", ""))
            mrr = latest_revenue.get("mrr", 0) or 0
            paid_users = latest_revenue.get("paid_users", 0) or 0
            free_users = latest_revenue.get("free_users", 1) or 1

            # Outcome score: blend of MRR signal (capped at $500/mo = 1.0) and retention rate
            mrr_score = min(mrr / 500.0, 1.0)
            retention_rate = paid_users / max(free_users, 1)
            retention_score = min(retention_rate * 5, 1.0)  # 20% retention = 1.0
            actual_outcome = (mrr_score * 0.6 + retention_score * 0.4)

            pairs.append({
                "app_name": app.get("name"),
                "predicted_fit": predicted_fit,
                "actual_outcome": round(actual_outcome, 3),
                "mrr": mrr,
                "paid_users": paid_users,
            })

        if len(pairs) < MIN_SAMPLE_SIZE:
            return _no_data_result(
                f"Only {len(pairs)} apps with both fit scores and revenue data. Need {MIN_SAMPLE_SIZE} for correlation.",
                sample_size=len(pairs),
                partial_data=pairs,
            )

        # Compute Pearson correlation
        correlation = _pearson_correlation(
            [p["predicted_fit"] for p in pairs],
            [p["actual_outcome"] for p in pairs],
        )
        passed = correlation >= CORRELATION_THRESHOLD

        logger.info(f"App fit eval: correlation={correlation:.4f}, sample={len(pairs)}, passed={passed}")

        return {
            "eval_name": "app_fit",
            "metric_name": "pearson_correlation",
            "metric_value": round(correlation, 4),
            "threshold": CORRELATION_THRESHOLD,
            "passed": passed,
            "details": {
                "sample_size": len(pairs),
                "correlation": round(correlation, 4),
                "pairs": pairs,
                "interpretation": _interpret_correlation(correlation),
            },
        }

    except Exception as e:
        logger.warning(f"App fit eval error: {e}")
        return {
            "eval_name": "app_fit",
            "metric_name": "pearson_correlation",
            "metric_value": None,
            "threshold": CORRELATION_THRESHOLD,
            "passed": False,
            "details": {"error": str(e)},
        }


def _no_data_result(note: str, sample_size: int = 0, partial_data: list | None = None) -> dict:
    return {
        "eval_name": "app_fit",
        "metric_name": "pearson_correlation",
        "metric_value": None,
        "threshold": CORRELATION_THRESHOLD,
        "passed": True,  # Not enough data to evaluate → pass
        "details": {
            "note": note,
            "sample_size": sample_size,
            "partial_data": partial_data or [],
        },
    }


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    """Compute Pearson r between two lists of equal length."""
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denom_x = (sum((xi - mean_x) ** 2 for xi in x)) ** 0.5
    denom_y = (sum((yi - mean_y) ** 2 for yi in y)) ** 0.5
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return numerator / (denom_x * denom_y)


def _interpret_correlation(r: float) -> str:
    if r >= 0.7:
        return "Strong positive correlation — app fit score is a reliable predictor of success"
    if r >= 0.5:
        return "Moderate correlation — app fit score is a useful signal but not definitive"
    if r >= 0.3:
        return "Weak correlation — app fit score needs recalibration"
    if r >= 0.0:
        return "Very weak correlation — app fit score is not predictive yet"
    return "Negative correlation — app fit score may be inversely calibrated; review scoring model"
