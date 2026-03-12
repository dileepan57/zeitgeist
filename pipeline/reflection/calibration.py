"""
Signal calibration engine.
Updates precision/recall per signal source based on outcomes.
"""
from datetime import date, timedelta
from loguru import logger
from pipeline.utils import db


def calibrate_signals():
    """
    For each recommendation made 90+ days ago, check its outcome
    and update signal performance stats.
    """
    logger.info("Calibrating signal performance...")

    cutoff = (date.today() - timedelta(days=90)).isoformat()
    recommendations = db.get_client().table("recommendations").select("*").lt("recommendation_date", cutoff).execute().data

    if not recommendations:
        logger.info("No mature recommendations to calibrate yet")
        return

    for rec in recommendations:
        rec_id = rec["id"]
        # Get outcome
        outcomes = db.select("outcomes", filters={"recommendation_id": rec_id})
        if not outcomes:
            continue

        outcome_type = outcomes[0]["outcome_type"]
        is_real = outcome_type == "REAL_MARKET"

        # Get signals that fired for this recommendation
        topic_signals = db.get_client().table("topic_signals").select("*").eq("run_id", rec["run_id"]).eq("topic_id", rec["topic_id"]).execute().data

        for signal in topic_signals:
            source = signal["signal_source"]
            fired = signal.get("fired", False)

            # Determine TP/FP/TN/FN
            if fired and is_real:
                update_type = "true_positives"
            elif fired and not is_real:
                update_type = "false_positives"
            elif not fired and is_real:
                update_type = "false_negatives"
            else:
                update_type = "true_negatives"

            # Increment counter
            existing = db.get_client().table("signal_performance").select("*").eq("signal_source", source).eq("domain", "all").execute().data

            if existing:
                row = existing[0]
                new_val = (row.get(update_type) or 0) + 1
                tp = row.get("true_positives", 0) + (1 if update_type == "true_positives" else 0)
                fp = row.get("false_positives", 0) + (1 if update_type == "false_positives" else 0)
                fn = row.get("false_negatives", 0) + (1 if update_type == "false_negatives" else 0)

                precision = tp / max(tp + fp, 1)
                recall = tp / max(tp + fn, 1)

                db.get_client().table("signal_performance").update({
                    update_type: new_val,
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "updated_at": "now()",
                }).eq("signal_source", source).eq("domain", "all").execute()

    logger.info("Signal calibration complete")


def get_calibrated_weights() -> dict[str, float]:
    """
    Return signal source weights based on historical precision.
    Used by scoring engine to weight signals dynamically.
    Falls back to equal weights if insufficient data.
    """
    perf = db.select("signal_performance", limit=50)

    weights = {}
    for row in perf:
        p = row.get("precision")
        if p is not None and p > 0:
            weights[row["signal_source"]] = p
        else:
            weights[row["signal_source"]] = 0.5  # neutral default

    # Normalize weights to sum to 1
    total = sum(weights.values())
    if total > 0:
        return {k: round(v / total, 4) for k, v in weights.items()}
    return weights
