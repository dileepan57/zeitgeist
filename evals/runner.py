"""
Eval runner: orchestrates all evals and stores results to eval_results table.
Can be run standalone or triggered via API.

Usage:
  python -m evals.runner               # all evals
  python -m evals.runner consistency   # specific eval
  python -m evals.runner --no-claude   # skip Claude-dependent evals
"""
import sys
from datetime import date
from loguru import logger


# Registry of all evals: (name, function, requires_claude)
def _get_eval_registry():
    from evals.consistency import run_consistency_eval
    from evals.calibration_eval import run_calibration_eval
    from evals.app_fit import run_app_fit_eval

    registry = [
        ("consistency", run_consistency_eval, False),
        ("calibration", run_calibration_eval, False),
        ("app_fit", run_app_fit_eval, False),
    ]

    # Claude-dependent evals — imported lazily so runner works without API key
    try:
        from evals.gap_analysis import run_gap_analysis_eval
        registry.append(("gap_analysis", run_gap_analysis_eval, True))
    except ImportError:
        pass

    try:
        from evals.opportunity_brief import run_opportunity_brief_eval
        registry.append(("opportunity_brief", run_opportunity_brief_eval, True))
    except ImportError:
        pass

    return registry


def run_all(include_claude: bool = True) -> list[dict]:
    """
    Run all evals. Returns list of result dicts.
    Set include_claude=False to skip evals that require Claude API calls.
    """
    registry = _get_eval_registry()
    results = []

    for name, fn, requires_claude in registry:
        if requires_claude and not include_claude:
            logger.info(f"Skipping {name} (requires Claude, include_claude=False)")
            continue

        logger.info(f"Running eval: {name}")
        try:
            result = fn()
            results.append(result)
            status = "PASS" if result.get("passed") else "FAIL"
            value = result.get("metric_value")
            logger.info(f"  [{status}] {name}: {result.get('metric_name')}={value}")
        except Exception as e:
            logger.error(f"Eval {name} crashed: {e}")
            results.append({
                "eval_name": name,
                "metric_name": "error",
                "metric_value": None,
                "threshold": None,
                "passed": False,
                "details": {"error": str(e)},
            })

    return results


def run_single(eval_name: str) -> dict:
    """Run a single eval by name."""
    registry = _get_eval_registry()
    for name, fn, _ in registry:
        if name == eval_name:
            return fn()
    raise ValueError(f"Unknown eval: {eval_name}. Available: {[n for n, _, _ in registry]}")


def persist_results(results: list[dict]) -> None:
    """Store eval results to the eval_results table."""
    try:
        from pipeline.utils.db import get_client
        client = get_client()
        today = date.today().isoformat()

        for result in results:
            metric_value = result.get("metric_value")
            client.table("eval_results").insert({
                "eval_name": result.get("eval_name"),
                "run_date": today,
                "metric_name": result.get("metric_name"),
                "metric_value": float(metric_value) if metric_value is not None else None,
                "threshold": result.get("threshold"),
                "passed": result.get("passed"),
                "details": result.get("details", {}),
            }).execute()

        logger.info(f"Persisted {len(results)} eval results")
    except Exception as e:
        logger.warning(f"Failed to persist eval results: {e}")


def print_summary(results: list[dict]) -> None:
    """Print a human-readable summary of eval results."""
    print("\n" + "=" * 60)
    print(f"EVAL RESULTS — {date.today()}")
    print("=" * 60)

    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    print(f"Overall: {passed}/{total} passed\n")

    for r in results:
        status = "✓ PASS" if r.get("passed") else "✗ FAIL"
        name = r.get("eval_name", "?")
        metric = r.get("metric_name", "?")
        value = r.get("metric_value")
        threshold = r.get("threshold")
        value_str = f"{value:.4f}" if isinstance(value, float) else str(value)
        threshold_str = f"{threshold}" if threshold is not None else "N/A"
        print(f"  {status}  {name:<25} {metric}={value_str} (threshold={threshold_str})")

    print("=" * 60 + "\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    no_claude = "--no-claude" in args
    specific = [a for a in args if not a.startswith("--")]

    if specific:
        result = run_single(specific[0])
        results = [result]
    else:
        results = run_all(include_claude=not no_claude)

    persist_results(results)
    print_summary(results)
