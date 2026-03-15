"""
Baseline-relative scoring.
Computes spike scores relative to 90-day rolling averages.
Suppresses evergreen topics unless they show exceptional spikes.
"""
import re
from loguru import logger

# Topics that are always high-volume — suppress unless extraordinary spike
EVERGREEN_TOPICS = {
    "climate change", "global warming", "artificial intelligence", "ai",
    "cryptocurrency", "bitcoin", "stock market", "covid", "election",
    "donald trump", "joe biden", "elon musk", "ukraine", "russia",
    "china", "inflation", "interest rates",
}

EVERGREEN_SPIKE_THRESHOLD = 3.0   # 3x baseline to fire for evergreen topics
STANDARD_SPIKE_THRESHOLD = 1.0    # 100% above baseline for normal topics


def compute_baseline_score(topic: str, signals: list[dict]) -> dict:
    """
    Given all signals for a topic, compute a composite baseline-relative score.
    Returns {baseline_score, spike_scores_by_source, is_evergreen, suppressed}
    """
    topic_lower = topic.lower()
    # Word-boundary match: avoid "ai" matching "ai_sleep_coach" as a substring
    topic_words = set(re.split(r"[\s_\-/]+", topic_lower))
    is_evergreen = any(
        ev in topic_words or topic_lower == ev or topic_lower.startswith(ev + " ")
        for ev in EVERGREEN_TOPICS
    )
    threshold = EVERGREEN_SPIKE_THRESHOLD if is_evergreen else STANDARD_SPIKE_THRESHOLD

    spike_scores = []
    suppressed_sources = []
    passing_sources = []

    for signal in signals:
        if not signal.get("fired"):
            continue

        spike_score = signal.get("spike_score", 0)
        source = signal.get("signal_source", "unknown")

        if spike_score is None:
            # If no baseline data (e.g. Reddit), use normalized score as-is
            spike_scores.append(0.5)
            passing_sources.append(source)
            continue

        if spike_score >= threshold:
            spike_scores.append(min(spike_score, 10.0))  # Cap at 10x
            passing_sources.append(source)
        elif is_evergreen and spike_score > 0:
            suppressed_sources.append(source)

    # Composite baseline score: geometric mean of spike scores
    if not spike_scores:
        composite = 0.0
    else:
        import math
        composite = math.exp(sum(math.log(max(s, 0.01)) for s in spike_scores) / len(spike_scores))

    # Normalize to 0-1
    baseline_score = min(composite / 5.0, 1.0)

    return {
        "baseline_score": round(baseline_score, 4),
        "spike_scores_by_source": dict(zip(passing_sources, spike_scores)),
        "is_evergreen": is_evergreen,
        "suppressed": is_evergreen and len(suppressed_sources) > len(passing_sources),
        "passing_sources": passing_sources,
    }
