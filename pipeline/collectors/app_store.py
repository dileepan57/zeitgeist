"""
App Store gap analysis signal collector.
Uses iTunes Search API (free, no key) to search for apps in topic categories.
Signal logic:
  - Few results (< 5) = unsaturated market gap = opportunity signal
  - Low average rating (< 3.5) with high engagement = unmet need signal
Fires if category_app_count < 5 OR avg_rating < 3.5.
signal_category: behavior
"""
import re
import time
from collections import defaultdict
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

ITUNES_SEARCH_API = "https://itunes.apple.com/search"
ITUNES_LOOKUP_API = "https://itunes.apple.com/lookup"

# Topic categories to probe for market gaps
# These are curated to reveal underserved niches
TOPIC_SEARCHES = [
    # AI & Productivity
    "AI writing assistant",
    "AI coding helper",
    "AI video editor",
    "AI photo editor",
    "AI email",
    "AI meeting notes",
    "AI homework helper",
    "local AI assistant",
    # Health & Wellness
    "menopause tracker",
    "perimenopause app",
    "ADHD focus timer",
    "autism communication",
    "chronic pain tracker",
    "migraine diary",
    "sleep apnea monitor",
    "continuous glucose monitor",
    # Climate & Environment
    "carbon footprint tracker",
    "EV charging locator",
    "solar panel monitor",
    "home energy monitor",
    "sustainability tracker",
    # Finance
    "crypto tax calculator",
    "DeFi portfolio tracker",
    "freelancer invoice",
    "tip calculator restaurant",
    "rent splitting",
    # Learning & Education
    "sign language learning",
    "dyslexia reading app",
    "language immersion",
    "coding for kids",
    "STEM experiment guide",
    # Social & Community
    "neighbor community app",
    "skill sharing local",
    "co-working space finder",
    "dog park finder",
    # Niche Tools
    "3D printing slicer",
    "drone flight planner",
    "ham radio logger",
    "mushroom identification",
    "foraging guide",
    "plant disease identifier",
    "soil test analyzer",
    # Emerging Tech
    "AR furniture preview",
    "spatial audio mixer",
    "voice cloning tool",
    "deepfake detector",
    "quantum computing simulator",
]

# Store IDs to query (1=US, 2=CA, 143441=US App Store)
COUNTRY = "us"

# Rating thresholds
MIN_APP_COUNT_FIRE = 5       # Fire if fewer than this many apps exist
MAX_RATING_FIRE = 3.5        # Fire if avg rating below this
MIN_RATING_COUNT_FOR_LOW = 50  # Minimum reviews needed to consider "low rating" signal


@retry_with_backoff(max_retries=3)
def _search_apps(term: str, limit: int = 25, media: str = "software") -> list[dict]:
    """
    Search iTunes App Store for apps matching a term.
    Returns list of app result dicts.
    """
    params = {
        "term": term,
        "country": COUNTRY,
        "media": media,
        "entity": "software",
        "limit": limit,
        "explicit": "No",
    }

    response = httpx.get(
        ITUNES_SEARCH_API,
        params=params,
        timeout=30,
        headers={"User-Agent": "zeitgeist/1.0"},
    )
    response.raise_for_status()
    data = response.json()
    return data.get("results", [])


def _compute_app_metrics(apps: list[dict]) -> dict:
    """
    Compute aggregate metrics from a list of app results.
    """
    if not apps:
        return {
            "count": 0,
            "avg_rating": 0.0,
            "avg_rating_count": 0.0,
            "total_ratings": 0,
            "top_apps": [],
        }

    ratings = [
        app.get("averageUserRating", 0.0)
        for app in apps
        if app.get("averageUserRating")
    ]
    rating_counts = [
        app.get("userRatingCount", 0)
        for app in apps
        if app.get("userRatingCount")
    ]

    avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
    avg_rating_count = sum(rating_counts) / len(rating_counts) if rating_counts else 0.0
    total_ratings = sum(rating_counts)

    top_apps = []
    for app in sorted(apps, key=lambda x: x.get("userRatingCount", 0), reverse=True)[:3]:
        top_apps.append({
            "name": app.get("trackName", ""),
            "rating": app.get("averageUserRating", 0),
            "rating_count": app.get("userRatingCount", 0),
            "seller": app.get("sellerName", ""),
        })

    return {
        "count": len(apps),
        "avg_rating": round(avg_rating, 2),
        "avg_rating_count": round(avg_rating_count, 0),
        "total_ratings": total_ratings,
        "top_apps": top_apps,
    }


def collect() -> list[dict]:
    """
    Searches App Store for topic categories to find market gaps.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, category_app_count,
                     avg_rating, gap_type}.
    Fires if category_app_count < 5 OR avg_rating < 3.5 with significant downloads.
    signal_category: behavior
    """
    logger.info("Collecting App Store gap signals...")
    results = []

    for term in TOPIC_SEARCHES:
        try:
            apps = _search_apps(term, limit=25)
            metrics = _compute_app_metrics(apps)

            count = metrics["count"]
            avg_rating = metrics["avg_rating"]
            total_ratings = metrics["total_ratings"]
            avg_rating_count = metrics["avg_rating_count"]

            # Determine gap type and fire conditions
            gap_type = None
            fired = False

            if count < MIN_APP_COUNT_FIRE:
                gap_type = "market_gap"
                fired = True
            elif avg_rating < MAX_RATING_FIRE and avg_rating > 0 and avg_rating_count >= MIN_RATING_COUNT_FOR_LOW:
                gap_type = "unmet_need"
                fired = True

            # Spike score: inverse of app count (fewer apps = higher signal)
            # + penalty for low ratings
            if count == 0:
                spike_score = 1.0  # Perfect gap
            else:
                gap_score = 1.0 / (1.0 + count / 5.0)
                dissatisfaction_score = max(0.0, (MAX_RATING_FIRE - avg_rating) / MAX_RATING_FIRE) if avg_rating > 0 else 0.0
                spike_score = min(gap_score + dissatisfaction_score * 0.5, 1.0)

            results.append({
                "topic": term,
                "raw_value": count,
                "baseline_value": 10.0,  # Baseline: saturated = 10+ good apps
                "spike_score": round(spike_score, 4),
                "signal_source": "app_store",
                "signal_category": "behavior",
                "fired": fired,
                "category_app_count": count,
                "avg_rating": avg_rating,
                "avg_rating_count": avg_rating_count,
                "total_ratings": total_ratings,
                "gap_type": gap_type,
                "top_apps": metrics["top_apps"],
            })

            logger.debug(
                f"App Store '{term}': {count} apps, "
                f"avg_rating={avg_rating:.1f}, fired={fired} ({gap_type})"
            )

            time.sleep(1.5)  # iTunes API rate limit

        except Exception as e:
            logger.warning(f"App Store: failed for '{term}': {e}")
            time.sleep(2)

    fired_count = sum(1 for r in results if r["fired"])
    gap_count = sum(1 for r in results if r.get("gap_type") == "market_gap")
    unmet_count = sum(1 for r in results if r.get("gap_type") == "unmet_need")

    logger.info(
        f"App Store: {len(results)} topics, {fired_count} fired "
        f"({gap_count} market gaps, {unmet_count} unmet needs)"
    )
    return results
