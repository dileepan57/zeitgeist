"""
Google Trends signal collector.
Uses pytrends (unofficial library) — free, no API key, but rate-limited.
Fetches daily trending searches and rising queries.
"""
import time
from pytrends.request import TrendReq
from loguru import logger
from pipeline.utils.rate_limiter import retry_with_backoff

GEO_LIST = ["US", "GB", "CA", "AU", "IN"]  # Major English markets


@retry_with_backoff(max_retries=3, base_delay=5.0)
def _get_trending(geo: str = "US") -> list[str]:
    """Get today's trending searches in a given country."""
    pytrends = TrendReq(hl="en-US", tz=0, timeout=(10, 30))
    time.sleep(2)  # Be respectful of rate limits
    df = pytrends.trending_searches(pn=geo.lower() if geo != "US" else "united_states")
    return df[0].tolist()


@retry_with_backoff(max_retries=3, base_delay=5.0)
def _get_rising_queries(keywords: list[str], geo: str = "US") -> dict[str, list[str]]:
    """Get rising related queries for a set of keywords."""
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
            trending = _get_trending(geo)
            for topic in trending:
                topic_geo_count[topic] = topic_geo_count.get(topic, 0) + 1
            time.sleep(2)
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
            "baseline_value": 1.0,  # 1 = single geo, treat multi-geo as above baseline
            "spike_score": round(geo_ratio, 4),
            "signal_source": "google_trends",
            "signal_category": "demand",
            "fired": geo_count >= 2,  # fires if trending in 2+ geographies
        })

    logger.info(f"Google Trends: {len(results)} topics, {sum(1 for r in results if r['fired'])} fired")
    return results
