"""
Actionability scorer.
Measures: Demand × Frustration × Supply Gap
This is the core differentiator — not just what's trending, but where the gap is.
"""
from loguru import logger

# Frustration keywords for text-based signals
FRUSTRATION_KEYWORDS = [
    "frustrating", "annoying", "terrible", "broken", "useless", "hate",
    "why doesn't", "why isn't", "can't find", "no app", "nobody built",
    "wish there was", "someone should", "need a", "looking for a",
    "alternative to", "better than", "disappointed", "avoid", "scam",
]

# Supply gap indicators
THIN_SUPPLY_INDICATORS = [
    "new", "first", "beta", "alpha", "launch", "introducing", "prototype",
    "open source", "just built", "mvp", "early access",
]


def score_frustration(signals: list[dict]) -> float:
    """
    Derive frustration score from available signal data.
    Returns 0-1: 0 = no frustration signal, 1 = high frustration.
    """
    frustration_signals = []

    for signal in signals:
        source = signal.get("signal_source", "")
        # Reddit complaint signals
        if source == "reddit" and signal.get("frustration_signal"):
            frustration_signals.append(0.8)

        # Negative tone from GDELT
        if source == "gdelt":
            tone = signal.get("avg_tone", 0)
            if tone and tone < -2:  # GDELT tone is -100 to +100
                frustration_signals.append(min(abs(tone) / 10, 1.0))

        # App Store ratings (added in Phase 2)
        if source == "app_store":
            avg_rating = signal.get("avg_rating", 5.0)
            if avg_rating < 3.5:
                frustration_signals.append((3.5 - avg_rating) / 3.5)

    if not frustration_signals:
        return 0.2  # Small default — assume some friction exists

    return round(min(sum(frustration_signals) / len(frustration_signals), 1.0), 4)


def score_supply_gap(signals: list[dict]) -> float:
    """
    Estimate supply gap from available signals.
    Returns 0-1: 0 = saturated market, 1 = clear supply gap.

    High gap indicators:
    - Few GitHub repos for the topic
    - No ProductHunt launches
    - No VC funding in Crunchbase
    - App Store category thin
    """
    gap_signals = []

    for signal in signals:
        source = signal.get("signal_source", "")

        # GitHub: few repos = opportunity
        if source == "github_trending":
            repo_count = signal.get("raw_value", 0)
            # Low GitHub activity despite other signals = supply gap
            if repo_count < 5:
                gap_signals.append(0.9)
            elif repo_count < 20:
                gap_signals.append(0.6)
            else:
                gap_signals.append(0.3)

        # ProductHunt: no recent launches = opportunity
        if source == "producthunt":
            launch_count = signal.get("raw_value", 0)
            if launch_count == 0:
                gap_signals.append(1.0)
            elif launch_count < 3:
                gap_signals.append(0.7)
            else:
                gap_signals.append(0.2)

        # Crunchbase: no funding = opportunity
        if source == "crunchbase":
            funding_count = signal.get("raw_value", 0)
            if funding_count == 0:
                gap_signals.append(0.9)
            elif funding_count < 3:
                gap_signals.append(0.6)
            else:
                gap_signals.append(0.1)

        # App Store: poor quality apps = opportunity
        if source == "app_store":
            avg_rating = signal.get("avg_rating", 4.0)
            app_count = signal.get("raw_value", 10)
            if app_count < 3:
                gap_signals.append(0.9)
            elif avg_rating < 3.0:
                gap_signals.append(0.8)
            elif avg_rating < 3.8:
                gap_signals.append(0.5)

    if not gap_signals:
        # No explicit supply data — moderate gap assumption
        return 0.4

    return round(sum(gap_signals) / len(gap_signals), 4)


def score_demand(signals: list[dict]) -> float:
    """
    Compute organic demand strength from demand + community category signals.
    Returns 0-1.
    """
    demand_sources = {"wikipedia", "google_trends", "reddit", "stackoverflow", "discord"}
    demand_scores = [
        min(s.get("spike_score", 0) or 0, 1.0)
        for s in signals
        if s.get("signal_source") in demand_sources and s.get("fired")
    ]

    if not demand_scores:
        return 0.0

    return round(sum(demand_scores) / len(demand_scores), 4)


def compute_actionability(signals: list[dict]) -> dict:
    """
    Composite actionability = demand × frustration × supply_gap.
    All factors normalized to 0-1.
    Returns full breakdown.
    """
    demand = score_demand(signals)
    frustration = score_frustration(signals)
    supply_gap = score_supply_gap(signals)

    # Multiplicative — all three must be present for high score
    composite = demand * frustration * supply_gap

    # Boost if frustration is very high (people are actively suffering)
    if frustration > 0.7:
        composite = min(composite * 1.3, 1.0)

    return {
        "demand_score": demand,
        "frustration_score": frustration,
        "supply_gap_score": supply_gap,
        "actionability_score": round(composite, 4),
    }
