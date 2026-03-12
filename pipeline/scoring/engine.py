"""
Main scoring engine.
Orchestrates all scoring modules and produces final opportunity scores.

Flow:
  raw signals → independence filter → baseline filter → actionability →
  timeline position → vocabulary fragmentation → final opportunity score
"""
from collections import defaultdict
from loguru import logger

from pipeline.scoring.independence import score_independence
from pipeline.scoring.baseline import compute_baseline_score
from pipeline.scoring.actionability import compute_actionability
from pipeline.scoring.timeline import classify_timeline, timeline_score
from pipeline.scoring.vocabulary import compute_fragmentation, extract_variants_from_signals
from pipeline.utils.entities import resolve_topic


# Opportunity score weights — self-reflection module calibrates these over time
WEIGHTS = {
    "independence": 0.25,
    "actionability": 0.35,
    "timeline": 0.20,
    "vocabulary_fragmentation": 0.10,
    "lead_indicator_ratio": 0.10,
}


def run(all_signals: list[dict]) -> list[dict]:
    """
    Main entry point.
    all_signals: flat list of signal dicts from all collectors.
    Each dict: {topic, signal_source, signal_category, raw_value,
                baseline_value, spike_score, fired, ...extra}

    Returns: list of scored topic dicts, sorted by opportunity_score descending.
    """
    logger.info(f"Scoring engine: processing {len(all_signals)} raw signals")

    # 1. Group signals by canonical topic
    topic_signals: dict[str, list[dict]] = defaultdict(list)
    all_raw_topics = [s["topic"] for s in all_signals]

    for signal in all_signals:
        canonical = resolve_topic(signal["topic"])
        signal["canonical_topic"] = canonical
        topic_signals[canonical].append(signal)

    logger.info(f"Resolved to {len(topic_signals)} unique topics")

    scored_topics = []

    for canonical_topic, signals in topic_signals.items():
        try:
            score = _score_topic(canonical_topic, signals, all_raw_topics)
            scored_topics.append(score)
        except Exception as e:
            logger.warning(f"Scoring failed for topic '{canonical_topic}': {e}")

    # Sort by opportunity score
    scored_topics.sort(key=lambda x: x["opportunity_score"], reverse=True)

    logger.info(f"Scored {len(scored_topics)} topics. Top: {scored_topics[0]['topic'] if scored_topics else 'none'}")
    return scored_topics


def _score_topic(topic: str, signals: list[dict], all_raw_topics: list[str]) -> dict:
    """Score a single topic across all dimensions."""

    # Step 1: Independence scoring
    independence_result = score_independence(signals)

    # Step 2: Baseline-relative scoring
    baseline_result = compute_baseline_score(topic, signals)

    # Skip suppressed evergreen topics with low spikes
    if baseline_result["suppressed"]:
        return _zero_score(topic, signals, "suppressed_evergreen")

    # Step 3: Actionability scoring
    actionability_result = compute_actionability(signals)

    # Step 4: Timeline classification
    timeline_result = classify_timeline(
        categories_fired=independence_result["adjusted_categories"],
    )
    tl_score = timeline_score(timeline_result["position"])

    # Step 5: Vocabulary fragmentation
    variants = extract_variants_from_signals(topic, all_raw_topics)
    vocab_result = compute_fragmentation(variants)

    # Step 6: Final composite score
    opportunity_score = (
        independence_result["independence_score"] * WEIGHTS["independence"] +
        actionability_result["actionability_score"] * WEIGHTS["actionability"] +
        tl_score * WEIGHTS["timeline"] +
        vocab_result["fragmentation_score"] * WEIGHTS["vocabulary_fragmentation"] +
        timeline_result["lead_indicator_ratio"] * WEIGHTS["lead_indicator_ratio"]
    )

    return {
        "topic": topic,
        "opportunity_score": round(opportunity_score, 4),
        "signal_count": len(signals),
        "fired_count": sum(1 for s in signals if s.get("fired")),

        # Independence
        "categories_fired": independence_result["categories_fired"],
        "adjusted_categories": independence_result["adjusted_categories"],
        "sources_fired": independence_result["sources_fired"],
        "independence_score": independence_result["independence_score"],
        "echo_detected": independence_result["echo_detected"],

        # Baseline
        "baseline_score": baseline_result["baseline_score"],
        "is_evergreen": baseline_result["is_evergreen"],

        # Actionability
        "demand_score": actionability_result["demand_score"],
        "frustration_score": actionability_result["frustration_score"],
        "supply_gap_score": actionability_result["supply_gap_score"],
        "actionability_score": actionability_result["actionability_score"],

        # Timeline
        "timeline_position": timeline_result["position"],
        "timeline_description": timeline_result["description"],
        "lead_indicator_ratio": timeline_result["lead_indicator_ratio"],
        "timeline_score": tl_score,

        # Vocabulary
        "vocabulary_fragmentation": vocab_result["fragmentation_score"],
        "dominant_term": vocab_result["dominant_term"],
        "variant_count": vocab_result["variant_count"],
        "vocab_interpretation": vocab_result["interpretation"],

        # Raw signals (for storage)
        "signals": signals,
    }


def _zero_score(topic: str, signals: list[dict], reason: str) -> dict:
    return {
        "topic": topic,
        "opportunity_score": 0.0,
        "signal_count": len(signals),
        "fired_count": 0,
        "categories_fired": [],
        "adjusted_categories": [],
        "sources_fired": [],
        "independence_score": 0.0,
        "echo_detected": False,
        "baseline_score": 0.0,
        "is_evergreen": True,
        "demand_score": 0.0,
        "frustration_score": 0.0,
        "supply_gap_score": 0.0,
        "actionability_score": 0.0,
        "timeline_position": "NONE",
        "timeline_description": reason,
        "lead_indicator_ratio": 0.0,
        "timeline_score": 0.0,
        "vocabulary_fragmentation": 0.0,
        "dominant_term": None,
        "variant_count": 0,
        "vocab_interpretation": reason,
        "signals": signals,
    }
