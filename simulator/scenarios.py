"""
Simulator scenario definitions.
Each scenario is a dict with:
  - name: unique identifier
  - description: what this tests
  - signals: list of synthetic signal dicts to inject into the scoring engine
  - topic: the topic name to query from results
"""
from datetime import datetime, timedelta


def _now():
    return datetime.utcnow()


def _ts(hours_ago: float) -> str:
    return (_now() - timedelta(hours=hours_ago)).isoformat()


def _signal(topic, source, category, spike_score=0.8, fired=True, **extra):
    return {
        "topic": topic,
        "signal_source": source,
        "signal_category": category,
        "spike_score": spike_score,
        "fired": fired,
        "raw_value": 100,
        "baseline_value": 50,
        **extra,
    }


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 1: Media Cascade (Echo Detection Test)
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_MEDIA_CASCADE = {
    "name": "media_cascade",
    "description": (
        "News fires, then demand spikes 24h later, community reacts 36h after news. "
        "Echo detection should recognize all three as one media cascade and collapse to 1 category."
    ),
    "topic": "new_diet_trend",
    "signals": [
        _signal("new_diet_trend", "gdelt", "media", spike_score=0.9,
                created_at=_ts(36)),
        _signal("new_diet_trend", "google_trends", "demand", spike_score=0.7,
                created_at=_ts(12)),
        _signal("new_diet_trend", "reddit", "community", spike_score=0.6,
                created_at=_ts(4)),
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 2: Early Emerging (Builder Only)
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_EARLY_EMERGING = {
    "name": "early_emerging",
    "description": (
        "Only builder signals fire (GitHub trending, ArXiv papers, USPTO filings). "
        "Should classify as EMERGING with high lead_indicator_ratio."
    ),
    "topic": "quantum_biosensors",
    "signals": [
        _signal("quantum_biosensors", "github_trending", "builder", spike_score=2.5),
        _signal("quantum_biosensors", "arxiv", "builder", spike_score=1.8),
        _signal("quantum_biosensors", "uspto", "builder", spike_score=1.2),
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 3: Full Convergence (PEAKING)
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_FULL_CONVERGENCE = {
    "name": "full_convergence",
    "description": (
        "All 6 categories fire simultaneously with high spikes. "
        "Should classify as PEAKING with independence_score = 1.0."
    ),
    "topic": "ai_agents",
    "signals": [
        _signal("ai_agents", "gdelt", "media", spike_score=5.0),
        _signal("ai_agents", "google_trends", "demand", spike_score=4.5),
        _signal("ai_agents", "app_store", "behavior", spike_score=3.8),
        _signal("ai_agents", "github_trending", "builder", spike_score=6.0),
        _signal("ai_agents", "reddit", "community", spike_score=4.2),
        _signal("ai_agents", "crunchbase", "money", spike_score=3.5),
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 4: Evergreen Modest Spike (Suppression)
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_EVERGREEN_SUPPRESSED = {
    "name": "evergreen_suppressed",
    "description": (
        "Evergreen topic 'artificial intelligence' with modest spike (1.5x). "
        "Should be suppressed (opportunity_score = 0.0)."
    ),
    "topic": "artificial intelligence",
    "signals": [
        _signal("artificial intelligence", "google_trends", "demand", spike_score=1.5),
        _signal("artificial intelligence", "reddit", "community", spike_score=2.0),
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 5: Evergreen Strong Spike (Not Suppressed)
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_EVERGREEN_STRONG = {
    "name": "evergreen_strong",
    "description": (
        "Evergreen topic 'artificial intelligence' with exceptional spike (3.5x+). "
        "Should NOT be suppressed — this is truly exceptional signal."
    ),
    "topic": "artificial intelligence",
    "signals": [
        _signal("artificial intelligence", "google_trends", "demand", spike_score=3.5),
        _signal("artificial intelligence", "reddit", "community", spike_score=4.0),
        _signal("artificial intelligence", "github_trending", "builder", spike_score=5.0),
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 6: High Frustration (Actionability Boost)
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_HIGH_FRUSTRATION = {
    "name": "high_frustration",
    "description": (
        "High Reddit complaint volume + low App Store rating (2.8) + thin supply. "
        "Should produce high frustration_score and high actionability."
    ),
    "topic": "period_tracking_app",
    "signals": [
        _signal("period_tracking_app", "google_trends", "demand", spike_score=2.0),
        _signal("period_tracking_app", "reddit", "community", spike_score=1.5,
                frustration_signal=True),
        _signal("period_tracking_app", "app_store", "behavior", spike_score=1.2,
                avg_rating=2.8, raw_value=5),
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 7: Vocabulary Fragmentation
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_VOCAB_FRAGMENTATION = {
    "name": "vocab_fragmentation",
    "description": (
        "30 topic variants with no dominant term — people call the same thing by many names. "
        "Should produce high fragmentation_score (> 0.7)."
    ),
    "topic": "longevity tracking",
    # The fragmentation test uses all_topics_collected, not just signals
    "signals": [
        _signal(f"longevity_variant_{i}", "reddit", "community", spike_score=0.5)
        for i in range(30)
    ],
    "all_topics": [
        "longevity tracking", "aging tracker", "lifespan optimizer", "healthspan monitor",
        "longevity protocol app", "anti-aging tracker", "biological age tool",
        "longevity score", "aging biomarkers", "healthspan optimizer",
        "epigenetic clock app", "NAD tracker", "inflammation tracker",
        "sleep longevity", "longevity habits", "biohacking longevity",
        "cellular health tracker", "telomere tracker", "metabolic age",
        "longevity coach app", "gut health longevity", "fasting longevity",
        "hormesis tracker", "HRV longevity", "longevity workout",
        "zone 2 longevity", "VO2 max tracker", "longevity nutrition",
        "protein for longevity", "longevity supplements tracker",
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 8: Zero Signals (Graceful Handling)
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_ZERO_SIGNALS = {
    "name": "zero_signals",
    "description": "Empty signal list — engine must return [] without raising.",
    "topic": None,
    "signals": [],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 9: Crystallizing Sweet Spot
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_CRYSTALLIZING = {
    "name": "crystallizing",
    "description": (
        "Builder + community signals with no media. "
        "This is the optimal build window — should classify as CRYSTALLIZING."
    ),
    "topic": "sleep_tracking_app",
    "signals": [
        _signal("sleep_tracking_app", "github_trending", "builder", spike_score=3.0),
        _signal("sleep_tracking_app", "reddit", "community", spike_score=2.5),
        _signal("sleep_tracking_app", "stackoverflow", "community", spike_score=1.8),
        _signal("sleep_tracking_app", "producthunt", "builder", spike_score=2.0, raw_value=1),
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO 10: Geographic Lead Signal
# ──────────────────────────────────────────────────────────────────────────────
SCENARIO_GEOGRAPHIC_LEAD = {
    "name": "geographic_lead",
    "description": (
        "Xiaohongshu (CN social) fires with geographic_lead_months, no US signals. "
        "Should not be suppressed — geographic lead is a valid EMERGING signal."
    ),
    "topic": "cn:beauty",
    "signals": [
        {
            "topic": "cn:beauty",
            "signal_source": "xiaohongshu",
            "signal_category": "demand",
            "spike_score": 0.8,
            "fired": True,
            "raw_value": 15,
            "geographic_lead_months": 18,
        }
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────────────
SCENARIOS = {
    s["name"]: s for s in [
        SCENARIO_MEDIA_CASCADE,
        SCENARIO_EARLY_EMERGING,
        SCENARIO_FULL_CONVERGENCE,
        SCENARIO_EVERGREEN_SUPPRESSED,
        SCENARIO_EVERGREEN_STRONG,
        SCENARIO_HIGH_FRUSTRATION,
        SCENARIO_VOCAB_FRAGMENTATION,
        SCENARIO_ZERO_SIGNALS,
        SCENARIO_CRYSTALLIZING,
        SCENARIO_GEOGRAPHIC_LEAD,
    ]
}


def get_all_scenarios() -> list[dict]:
    return list(SCENARIOS.values())
