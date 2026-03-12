"""
Timeline position classifier.
Classifies topics as EMERGING → CRYSTALLIZING → MAINSTREAM → PEAKING → DECLINING.
Based on which signal categories are firing and their relative weights.
"""

# Signal categories ordered by lead time (earliest first)
LEAD_ORDER = ["builder", "community", "money", "behavior", "demand", "media"]

# Timeline position rules (evaluated in order, first match wins)
# Each rule specifies: required categories present, required categories absent
TIMELINE_RULES = [
    {
        "position": "EMERGING",
        "required_present": ["builder"],
        "required_absent": ["media", "demand"],
        "description": "Builder signals only — too early for mainstream",
    },
    {
        "position": "CRYSTALLIZING",
        "required_present": ["builder", "community"],
        "required_absent": ["media"],
        "description": "Community forming around builder activity — sweet spot",
    },
    {
        "position": "CRYSTALLIZING",
        "required_present": ["community", "behavior"],
        "required_absent": ["media"],
        "description": "User behavior + community without media — pre-mainstream",
    },
    {
        "position": "MAINSTREAM",
        "required_present": ["demand", "media"],
        "required_absent": [],
        "description": "Search + news firing — mainstream attention",
    },
    {
        "position": "MAINSTREAM",
        "required_present": ["demand", "community", "behavior"],
        "required_absent": [],
        "description": "Multi-channel mainstream without media dependence",
    },
    {
        "position": "PEAKING",
        "required_present": ["builder", "community", "behavior", "demand", "media"],
        "required_absent": [],
        "description": "All signals firing — at or near peak",
    },
]


def classify_timeline(
    categories_fired: list[str],
    velocity_score: float = 0.0,
    is_declining: bool = False,
) -> dict:
    """
    Given the set of categories that fired, return timeline position.

    categories_fired: list of category names
    velocity_score: positive = accelerating, negative = decelerating
    is_declining: True if signals are declining vs. prior week
    """
    categories = set(categories_fired)

    if is_declining and len(categories) > 0:
        return {
            "position": "DECLINING",
            "description": "Signals falling — contrarian build opportunity",
            "lead_indicator_ratio": _lead_ratio(categories),
        }

    # Check rules in order
    for rule in TIMELINE_RULES:
        required = set(rule["required_present"])
        absent = set(rule["required_absent"])

        if required.issubset(categories) and not absent.intersection(categories):
            return {
                "position": rule["position"],
                "description": rule["description"],
                "lead_indicator_ratio": _lead_ratio(categories),
            }

    # Default based on what's firing
    if not categories:
        return {"position": "NONE", "description": "No signals", "lead_indicator_ratio": 0.0}

    if "media" in categories and len(categories) == 1:
        return {
            "position": "MAINSTREAM",
            "description": "Media-driven only",
            "lead_indicator_ratio": 0.0,
        }

    if len(categories) >= 4:
        return {
            "position": "PEAKING",
            "description": "High signal density",
            "lead_indicator_ratio": _lead_ratio(categories),
        }

    return {
        "position": "CRYSTALLIZING",
        "description": "Multi-signal, building",
        "lead_indicator_ratio": _lead_ratio(categories),
    }


def _lead_ratio(categories: set[str]) -> float:
    """Ratio of early-tier signals (builder, community) to total."""
    early = {"builder", "community"}
    if not categories:
        return 0.0
    return round(len(early.intersection(categories)) / len(categories), 4)


def timeline_score(position: str) -> float:
    """
    Convert timeline position to a numeric score.
    CRYSTALLIZING is optimal — peaks at 1.0.
    """
    scores = {
        "EMERGING": 0.6,       # Early but uncertain
        "CRYSTALLIZING": 1.0,  # Best build window
        "MAINSTREAM": 0.7,     # Validated but competitive
        "PEAKING": 0.3,        # Late, window closing
        "DECLINING": 0.5,      # Contrarian play
        "NONE": 0.0,
    }
    return scores.get(position, 0.0)
