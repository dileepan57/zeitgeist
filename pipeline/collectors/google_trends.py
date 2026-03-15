"""
Google Trends signal collector.
Uses Google Trends RSS feed (public, no API key, stable) for daily trending searches,
and pytrends for rising related queries.
"""
import time
import httpx
import feedparser
from loguru import logger
from pipeline.utils.rate_limiter import retry_with_backoff

# Google Trends daily trending RSS — stable public endpoint
# Maps geo code → RSS URL
GEO_RSS = {
    "US": "https://trends.google.com/trending/rss?geo=US",
    "GB": "https://trends.google.com/trending/rss?geo=GB",
    "CA": "https://trends.google.com/trending/rss?geo=CA",
    "AU": "https://trends.google.com/trending/rss?geo=AU",
    "IN": "https://trends.google.com/trending/rss?geo=IN",
}

GEO_LIST = list(GEO_RSS.keys())


@retry_with_backoff(max_retries=3, base_delay=3.0)
def _get_trending_rss(geo: str = "US") -> list[str]:
    """Fetch today's trending searches via Google Trends RSS feed."""
    url = GEO_RSS[geo]
    resp = httpx.get(url, timeout=15, follow_redirects=True,
                     headers={"User-Agent": "zeitgeist/1.0 trend-monitor"})
    resp.raise_for_status()
    feed = feedparser.parse(resp.text)
    return [entry.title for entry in feed.entries if entry.get("title")]


@retry_with_backoff(max_retries=2, base_delay=5.0)
def _get_rising_queries(keywords: list[str], geo: str = "US") -> dict[str, list[str]]:
    """Get rising related queries for a set of keywords via pytrends."""
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
        time.sleep(3)
        pytrends.build_payload(keywords[:5], cat=0, timeframe="now 7-d", geo=geo)
        related = pytrends.related_queries()
        rising = {}
        for kw in keywords[:5]:
            try:
                df = related.get(kw, {}).get("rising")
                if df is not None and not df.empty:
                    rising[kw] = df["query"].tolist()[:10]
            except Exception:
                pass
        return rising
    except Exception as e:
        logger.debug(f"Rising queries unavailable: {e}")
        return {}


def collect() -> list[dict]:
    """
    Returns list of {topic, raw_value, baseline_value, spike_score, signal_source, signal_category}
    """
    logger.info("Collecting Google Trends signals...")
    results = []
    topic_geo_count: dict[str, int] = {}

    # Collect trending from multiple geographies (cross-geo = stronger signal)
    for geo in GEO_LIST:
        try:
            trending = _get_trending_rss(geo)
            for topic in trending:
                topic_geo_count[topic] = topic_geo_count.get(topic, 0) + 1
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Google Trends: failed for geo {geo}: {e}")

    if not topic_geo_count:
        logger.warning("Google Trends: no data collected")
        return results

    # Score by cross-geography presence
    max_geo = len(GEO_LIST)
    for topic, geo_count in sorted(topic_geo_count.items(), key=lambda x: x[1], reverse=True)[:60]:
        geo_ratio = geo_count / max_geo
        results.append({
            "topic": topic,
            "raw_value": geo_count,
            "baseline_value": 1.0,
            "spike_score": round(geo_ratio, 4),
            "signal_source": "google_trends",
            "signal_category": "demand",
            "fired": geo_count >= 2,  # fires if trending in 2+ geographies
        })

    logger.info(f"Google Trends: {len(results)} topics, {sum(1 for r in results if r['fired'])} fired")
    return results
