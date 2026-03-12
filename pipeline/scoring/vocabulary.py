"""
Vocabulary fragmentation detector.
When people describe the same problem with many different phrases and no
dominant solution keyword exists, it signals an unmapped category.
High fragmentation = opportunity to name and own the space.
"""
import numpy as np
from collections import Counter
from loguru import logger


def compute_fragmentation(topic_variants: list[str], threshold: float = 0.7) -> dict:
    """
    Given a list of topic variant strings (from different signal sources),
    compute vocabulary fragmentation.

    High fragmentation score = many different phrases, no dominant one.
    Low fragmentation = one dominant term (market may be named/owned already).

    Returns {fragmentation_score, dominant_term, variant_count, interpretation}
    """
    if not topic_variants:
        return {"fragmentation_score": 0.0, "dominant_term": None, "variant_count": 0, "interpretation": "no data"}

    # Count frequency of each variant
    counts = Counter(topic_variants)
    total = len(topic_variants)
    most_common_term, most_common_count = counts.most_common(1)[0]

    # Dominance ratio: how concentrated is attention on one term?
    dominance_ratio = most_common_count / total

    # Fragmentation = 1 - dominance (high when no single term dominates)
    fragmentation_score = 1.0 - dominance_ratio

    # Unique variety score: more variants = more fragmented
    variety_score = min(len(counts) / 20.0, 1.0)  # normalize to 20 variants max

    # Combined fragmentation
    combined = (fragmentation_score * 0.6 + variety_score * 0.4)

    if combined > 0.7:
        interpretation = "High fragmentation — category likely unmapped, no dominant solution"
    elif combined > 0.4:
        interpretation = "Moderate fragmentation — emerging naming, solution forming"
    else:
        interpretation = "Low fragmentation — dominant term/brand exists, market named"

    return {
        "fragmentation_score": round(combined, 4),
        "dominance_ratio": round(dominance_ratio, 4),
        "dominant_term": most_common_term,
        "variant_count": len(counts),
        "total_mentions": total,
        "interpretation": interpretation,
    }


def extract_variants_from_signals(topic: str, all_topics_collected: list[str]) -> list[str]:
    """
    From the full list of topics collected across all sources,
    find all strings that are semantically related to the canonical topic.
    This requires the entity resolution module.

    Returns list of variant strings.
    """
    topic_lower = topic.lower()
    variants = []

    for t in all_topics_collected:
        t_lower = t.lower()
        # Simple substring check for now — entity resolution handles semantics
        if topic_lower in t_lower or t_lower in topic_lower:
            variants.append(t)
        # Also check for word overlap
        elif len(set(topic_lower.split()) & set(t_lower.split())) >= 2:
            variants.append(t)

    return variants
