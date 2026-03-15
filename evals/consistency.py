"""
Eval 1: Consistency
Run the scoring engine 5 times with identical synthetic signals.
Assert: std_dev(opportunity_scores) < 0.05 (deterministic scoring).

No Claude API calls needed — pure scoring layer evaluation.
"""
import statistics
from loguru import logger
from unittest.mock import patch


CONSISTENCY_RUNS = 5
STD_DEV_THRESHOLD = 0.05

# Fixed synthetic signals for consistency testing
CONSISTENCY_SIGNALS = [
    {"topic": "longevity_tracking", "signal_source": "github_trending",
     "signal_category": "builder", "spike_score": 3.2, "fired": True,
     "raw_value": 50, "baseline_value": 15},
    {"topic": "longevity_tracking", "signal_source": "reddit",
     "signal_category": "community", "spike_score": 2.1, "fired": True,
     "raw_value": 800, "baseline_value": 300, "frustration_signal": True},
    {"topic": "longevity_tracking", "signal_source": "google_trends",
     "signal_category": "demand", "spike_score": 1.8, "fired": True,
     "raw_value": 72, "baseline_value": 40},
    {"topic": "longevity_tracking", "signal_source": "youtube",
     "signal_category": "media", "spike_score": 2.5, "fired": True,
     "raw_value": 200, "baseline_value": 80},
    {"topic": "longevity_tracking", "signal_source": "producthunt",
     "signal_category": "builder", "spike_score": 1.5, "fired": True,
     "raw_value": 2, "baseline_value": 0},
]


def run_consistency_eval() -> dict:
    """
    Run scoring engine N times with identical inputs.
    Measure variance in opportunity_score.
    """
    from pipeline.scoring.engine import run as engine_run

    scores = []
    errors = []

    for i in range(CONSISTENCY_RUNS):
        try:
            # Deep-copy signals to avoid mutation between runs
            import copy
            signals = copy.deepcopy(CONSISTENCY_SIGNALS)

            with patch("pipeline.scoring.engine.resolve_topic", side_effect=lambda t: t):
                results = engine_run(signals)

            topic_result = next(
                (r for r in results if r.get("topic") == "longevity_tracking"),
                results[0] if results else None,
            )
            if topic_result:
                scores.append(topic_result["opportunity_score"])
            else:
                errors.append(f"Run {i+1}: no result returned")

        except Exception as e:
            errors.append(f"Run {i+1}: {e}")

    if not scores:
        return {
            "eval_name": "consistency",
            "metric_name": "std_dev",
            "metric_value": None,
            "threshold": STD_DEV_THRESHOLD,
            "passed": False,
            "details": {"errors": errors, "scores": []},
        }

    std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0
    mean_score = statistics.mean(scores)
    passed = std_dev < STD_DEV_THRESHOLD

    logger.info(f"Consistency eval: scores={[round(s, 4) for s in scores]}, std_dev={std_dev:.4f}, passed={passed}")

    return {
        "eval_name": "consistency",
        "metric_name": "std_dev",
        "metric_value": round(std_dev, 6),
        "threshold": STD_DEV_THRESHOLD,
        "passed": passed,
        "details": {
            "runs": CONSISTENCY_RUNS,
            "scores": [round(s, 4) for s in scores],
            "mean": round(mean_score, 4),
            "std_dev": round(std_dev, 6),
            "errors": errors,
        },
    }
