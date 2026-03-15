"""
Eval 2: Score Calibration (Brier Score)
Pull all recommendations with outcomes from DB.
Compute Brier score: mean((confidence - actual)^2)
Threshold: Brier score < 0.25 = acceptable calibration.

No Claude API calls needed — purely computes against historical outcomes.
Starts with no data; accumulates over weeks.
"""
from loguru import logger

BRIER_THRESHOLD = 0.25


def run_calibration_eval() -> dict:
    """
    Compute Brier score from historical recommendations + outcomes.
    Returns calibration eval result.
    """
    try:
        from pipeline.utils.db import get_client
        client = get_client()

        # Fetch recommendations that have outcomes
        recs = client.table("recommendations").select("*").execute().data
        if not recs:
            return {
                "eval_name": "calibration",
                "metric_name": "brier_score",
                "metric_value": None,
                "threshold": BRIER_THRESHOLD,
                "passed": True,  # No data yet → pass (not enough to evaluate)
                "details": {"note": "No historical recommendations yet. Will accumulate over time.", "sample_size": 0},
            }

        # Build recommendation_id → confidence mapping
        rec_by_id = {r["id"]: r.get("confidence_score", 0.5) for r in recs}

        # Fetch outcomes
        outcomes = client.table("outcomes").select("*").execute().data
        if not outcomes:
            return {
                "eval_name": "calibration",
                "metric_name": "brier_score",
                "metric_value": None,
                "threshold": BRIER_THRESHOLD,
                "passed": True,
                "details": {"note": "No outcomes tagged yet.", "sample_size": 0},
            }

        # Compute Brier score
        brier_pairs = []
        for outcome in outcomes:
            rec_id = outcome.get("recommendation_id")
            if rec_id not in rec_by_id:
                continue
            confidence = rec_by_id[rec_id] or 0.5
            # REAL_MARKET = 1, others = 0
            actual = 1.0 if outcome.get("outcome_type") == "REAL_MARKET" else 0.0
            brier_pairs.append((confidence, actual))

        if not brier_pairs:
            return {
                "eval_name": "calibration",
                "metric_name": "brier_score",
                "metric_value": None,
                "threshold": BRIER_THRESHOLD,
                "passed": True,
                "details": {"note": "Recommendations exist but none have REAL_MARKET outcomes yet.", "sample_size": 0},
            }

        brier_score = sum((conf - act) ** 2 for conf, act in brier_pairs) / len(brier_pairs)
        passed = brier_score < BRIER_THRESHOLD

        # Compute calibration by decile
        decile_stats = _compute_decile_calibration(brier_pairs)

        logger.info(f"Calibration eval: brier_score={brier_score:.4f}, sample={len(brier_pairs)}, passed={passed}")

        return {
            "eval_name": "calibration",
            "metric_name": "brier_score",
            "metric_value": round(brier_score, 6),
            "threshold": BRIER_THRESHOLD,
            "passed": passed,
            "details": {
                "sample_size": len(brier_pairs),
                "brier_score": round(brier_score, 6),
                "decile_calibration": decile_stats,
                "overall_real_rate": round(sum(a for _, a in brier_pairs) / len(brier_pairs), 3),
            },
        }

    except Exception as e:
        logger.warning(f"Calibration eval error: {e}")
        return {
            "eval_name": "calibration",
            "metric_name": "brier_score",
            "metric_value": None,
            "threshold": BRIER_THRESHOLD,
            "passed": False,
            "details": {"error": str(e)},
        }


def _compute_decile_calibration(pairs: list[tuple]) -> list[dict]:
    """
    Group predictions by confidence decile and compare to actual rate.
    Reveals whether confidence 0.7 actually materializes 70% of the time.
    """
    buckets: dict[int, list] = {i: [] for i in range(10)}
    for conf, actual in pairs:
        bucket = min(int(conf * 10), 9)
        buckets[bucket].append(actual)

    result = []
    for bucket, actuals in buckets.items():
        if not actuals:
            continue
        result.append({
            "confidence_range": f"{bucket/10:.1f}-{(bucket+1)/10:.1f}",
            "predicted_rate": round((bucket + 0.5) / 10, 2),
            "actual_rate": round(sum(actuals) / len(actuals), 3),
            "sample_size": len(actuals),
        })

    return result
