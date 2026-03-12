"""
Crunchbase funding signal collector.
Uses Crunchbase Basic API if key available, otherwise uses public data.
Tracks recent funding rounds by category as a money signal.
signal_category: money
"""
import os
import httpx
import time
from collections import defaultdict
from loguru import logger
from dotenv import load_dotenv
from pipeline.utils.rate_limiter import retry_with_backoff

load_dotenv()

CRUNCHBASE_API = "https://api.crunchbase.com/api/v4"

# Tech categories to watch in Crunchbase
CATEGORIES = [
    "artificial-intelligence", "machine-learning", "climate-tech",
    "health-care", "fintech", "edtech", "biotech", "cybersecurity",
    "developer-tools", "no-code", "robotics", "quantum-computing",
    "augmented-reality", "creator-economy", "mental-health",
]


@retry_with_backoff(max_retries=3)
def _fetch_recent_funding(category: str, api_key: str) -> list[dict]:
    """Fetch recent funding rounds for a category via Crunchbase API."""
    params = {
        "user_key": api_key,
        "category_uuids": category,
        "announced_on_gte": _days_ago(30),
        "limit": 25,
    }
    response = httpx.get(
        f"{CRUNCHBASE_API}/searches/funding_rounds",
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    return response.json().get("entities", [])


def _days_ago(n: int) -> str:
    from datetime import date, timedelta
    return (date.today() - timedelta(days=n)).isoformat()


def _collect_with_api(api_key: str) -> list[dict]:
    """Collect using Crunchbase API."""
    results = []
    category_counts: dict[str, int] = defaultdict(int)
    category_amounts: dict[str, float] = defaultdict(float)

    for category in CATEGORIES:
        try:
            rounds = _fetch_recent_funding(category, api_key)
            for r in rounds:
                props = r.get("properties", {})
                amount = props.get("money_raised_usd", 0) or 0
                category_counts[category] += 1
                category_amounts[category] += amount
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Crunchbase: failed for {category}: {e}")

    if not category_counts:
        return results

    max_count = max(category_counts.values())
    for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        normalized = count / max_count
        results.append({
            "topic": category.replace("-", " "),
            "raw_value": count,
            "baseline_value": None,
            "spike_score": round(normalized, 4),
            "signal_source": "crunchbase",
            "signal_category": "money",
            "fired": count >= 3,
            "total_funding_usd": round(category_amounts[category]),
        })

    return results


def _collect_fallback() -> list[dict]:
    """
    Fallback: use public Crunchbase news feed via RSS/GDELT for funding mentions.
    This is a best-effort approach when no API key is available.
    """
    logger.info("Crunchbase: no API key, using funding news fallback via GDELT")
    try:
        import feedparser
        # GDELT covers TechCrunch, VentureBeat funding news
        feed = feedparser.parse("https://feeds.feedburner.com/venturebeat/SZYF")
        topic_counts: dict[str, int] = defaultdict(int)

        for entry in feed.entries[:30]:
            title = entry.get("title", "").lower()
            summary = entry.get("summary", "").lower()
            content = f"{title} {summary}"

            for cat in CATEGORIES:
                readable = cat.replace("-", " ")
                if readable in content or any(w in content for w in readable.split()):
                    topic_counts[readable] += 1

        if not topic_counts:
            return []

        max_count = max(topic_counts.values())
        return [
            {
                "topic": topic,
                "raw_value": count,
                "baseline_value": None,
                "spike_score": round(count / max_count, 4),
                "signal_source": "crunchbase",
                "signal_category": "money",
                "fired": count >= 2,
            }
            for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        ]
    except Exception as e:
        logger.warning(f"Crunchbase fallback failed: {e}")
        return []


def collect() -> list[dict]:
    logger.info("Collecting Crunchbase signals...")
    api_key = os.environ.get("CRUNCHBASE_API_KEY")

    if api_key:
        results = _collect_with_api(api_key)
    else:
        results = _collect_fallback()

    logger.info(f"Crunchbase: {len(results)} topics, {sum(1 for r in results if r.get('fired')) } fired")
    return results
