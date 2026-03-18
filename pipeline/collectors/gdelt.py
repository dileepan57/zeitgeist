"""
GDELT Project signal collector.
Free, no auth, monitors news coverage across 1000s of global outlets.
Uses GDELT GKG (Global Knowledge Graph) for topic/theme extraction.
"""
import httpx
from datetime import date, timedelta
from collections import defaultdict
from loguru import logger
from pipeline.utils.rate_limiter import retry_with_backoff

GDELT_API = "https://api.gdeltproject.org/api/v2/tv/tv"
GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


@retry_with_backoff(max_retries=3)
def _fetch_top_themes(timespan: str = "1d") -> list[dict]:
    """
    Fetch top themes/topics from GDELT document API.
    Returns list of {theme, count, tone} dicts.
    """
    params = {
        "query": "sourcelang:english",
        "mode": "artlist",
        "maxrecords": 250,
        "timespan": timespan,
        "format": "json",
    }
    response = httpx.get(GDELT_DOC_API, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("articles", [])


@retry_with_backoff(max_retries=3)
def _fetch_trending_topics(query: str = "", timespan: str = "48h") -> dict:
    """Use GDELT's timeline API to detect news volume spikes for a topic."""
    params = {
        "query": query or "sourcelang:english",
        "mode": "timelinevol",
        "timespan": timespan,
        "format": "json",
    }
    response = httpx.get(GDELT_DOC_API, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


@retry_with_backoff(max_retries=3)
def _fetch_top_coverage(timespan: str = "24h", max_records: int = 250) -> list[dict]:
    """Fetch most-covered topics from GDELT."""
    params = {
        "query": "sourcelang:english",
        "mode": "artlist",
        "maxrecords": max_records,
        "timespan": timespan,
        "sort": "hybridrel",
        "format": "json",
    }
    response = httpx.get(GDELT_DOC_API, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("articles", [])


def _extract_topics_from_articles(articles: list[dict]) -> dict[str, dict]:
    """Extract themes and named entities from GDELT articles."""
    topic_counts: dict[str, int] = defaultdict(int)
    topic_tone: dict[str, list[float]] = defaultdict(list)

    for article in articles:
        # Extract from title words as a simple proxy
        title = article.get("title", "")
        tone = article.get("tone", 0)

        # GDELT provides themes in the article metadata
        themes = article.get("themes", "").split(";") if article.get("themes") else []
        for theme in themes:
            if theme and len(theme) > 3:
                clean = theme.replace("_", " ").lower().strip()
                topic_counts[clean] += 1
                topic_tone[clean].append(float(tone) if tone else 0.0)

        # Also use title-based extraction
        if title:
            # Simple: use title as-is for named entity extraction
            topic_counts[title[:60]] += 1

    return {
        topic: {
            "count": count,
            "avg_tone": sum(topic_tone.get(topic, [0])) / max(len(topic_tone.get(topic, [0])), 1),
        }
        for topic, count in topic_counts.items()
        if count >= 2
    }


def collect() -> list[dict]:
    """
    Returns list of {topic, raw_value, baseline_value, spike_score, signal_source, signal_category}
    """
    logger.info("Collecting GDELT signals...")
    results = []

    try:
        # Fetch last 24h vs last 7d to compute spike
        # Sleep between calls to avoid GDELT rate limiting
        import time
        recent_articles = _fetch_top_coverage(timespan="24h", max_records=250)
        time.sleep(15)
        baseline_articles = _fetch_top_coverage(timespan="7d", max_records=250)
    except Exception as e:
        logger.error(f"GDELT fetch failed: {e}")
        return results

    recent_topics = _extract_topics_from_articles(recent_articles)
    baseline_topics = _extract_topics_from_articles(baseline_articles)

    # Daily avg from 7d baseline
    for topic, data in recent_topics.items():
        recent_count = data["count"]
        baseline_count = baseline_topics.get(topic, {}).get("count", 0)
        daily_baseline = max(baseline_count / 7, 1)

        spike_score = (recent_count - daily_baseline) / daily_baseline

        if recent_count >= 3:  # Minimum coverage threshold
            results.append({
                "topic": topic,
                "raw_value": recent_count,
                "baseline_value": round(daily_baseline, 2),
                "spike_score": round(spike_score, 4),
                "signal_source": "gdelt",
                "signal_category": "media",
                "fired": spike_score > 0.5 and recent_count >= 5,
                "avg_tone": round(data["avg_tone"], 2),
            })

    results.sort(key=lambda x: x["spike_score"], reverse=True)
    results = results[:60]

    logger.info(f"GDELT: {len(results)} topics, {sum(1 for r in results if r['fired'])} fired")
    return results
