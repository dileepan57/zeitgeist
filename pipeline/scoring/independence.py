"""
Signal Independence Scorer.
Core principle: one point per CATEGORY, not per signal.
Detects causal echo chains (news → search within 48h → discount).
"""
from datetime import datetime, timedelta
from loguru import logger

SIGNAL_CATEGORIES = {
    "wikipedia": "demand",
    "google_trends": "demand",
    "reddit": "community",
    "gdelt": "media",
    "youtube": "media",
    "github_trending": "builder",
    "arxiv": "builder",
    "uspto": "builder",
    "sbir": "builder",
    "itunes": "media",
    "producthunt": "builder",
    "markets": "money",
    "kickstarter": "money",
    "crunchbase": "money",
    "app_store": "behavior",
    "amazon_movers": "behavior",
    "job_postings": "behavior",
    "discord": "community",
    "stackoverflow": "community",
    "substack": "media",
    "federal_register": "builder",
    "xiaohongshu": "demand",
}

# Which categories are "downstream" of which (for echo detection)
# If a "source" fires and then a "downstream" fires within 48h,
# the downstream is discounted as an echo.
ECHO_PAIRS = [
    ("media", "demand"),   # news story → search spike
    ("media", "community"), # news story → Reddit reaction
]


def score_independence(signals: list[dict]) -> dict:
    """
    Given a list of fired signals for a topic, compute:
    - categories_fired: unique categories
    - independence_score: 0-1 (unique_categories / 6)
    - echo_detected: whether any echo chains were found
    - adjusted_categories: categories after echo removal

    signals: list of {signal_source, signal_category, fired, created_at (optional)}
    """
    fired = [s for s in signals if s.get("fired")]

    if not fired:
        return {
            "categories_fired": [],
            "independence_score": 0.0,
            "echo_detected": False,
            "adjusted_categories": [],
            "sources_fired": [],
        }

    sources_fired = [s["signal_source"] for s in fired]
    categories_by_source = {s["signal_source"]: s["signal_category"] for s in fired}
    categories_fired = list(set(categories_by_source.values()))

    # Echo detection: check if media fired first and demand/community followed
    echo_detected = False
    adjusted_categories = set(categories_fired)

    if "media" in categories_fired:
        for source_cat, downstream_cat in ECHO_PAIRS:
            if source_cat in categories_fired and downstream_cat in categories_fired:
                # Check if timing data available
                media_signals = [s for s in fired if s.get("signal_category") == source_cat]
                downstream_signals = [s for s in fired if s.get("signal_category") == downstream_cat]

                if media_signals and downstream_signals:
                    # If timestamps available, check 48h window
                    media_ts = media_signals[0].get("created_at")
                    downstream_ts = downstream_signals[0].get("created_at")

                    if media_ts and downstream_ts:
                        try:
                            m_time = datetime.fromisoformat(str(media_ts))
                            d_time = datetime.fromisoformat(str(downstream_ts))
                            if abs((d_time - m_time).total_seconds()) < 48 * 3600:
                                echo_detected = True
                                # Remove downstream echo category
                                adjusted_categories.discard(downstream_cat)
                                logger.debug(f"Echo detected: {source_cat} → {downstream_cat}")
                        except Exception:
                            pass

    adjusted_categories = list(adjusted_categories)
    independence_score = len(adjusted_categories) / 6.0  # max 6 categories

    return {
        "categories_fired": categories_fired,
        "sources_fired": sources_fired,
        "independence_score": round(independence_score, 4),
        "echo_detected": echo_detected,
        "adjusted_categories": adjusted_categories,
    }
