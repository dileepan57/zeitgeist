"""
YouTube Data API v3 signal collector.
Uses YOUTUBE_API_KEY env var to fetch trending videos across US, UK, CA regions.
Extracts topics from titles and tags using keyword extraction.
Fires if a topic appears trending in 2+ regions — cross-region = strong media signal.
signal_category: media
"""
import os
import re
import time
from collections import defaultdict, Counter
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
REGIONS = ["US", "GB", "CA"]
MAX_RESULTS = 50  # per region, per category

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can",
    "in", "on", "at", "to", "for", "of", "and", "or", "but",
    "not", "with", "this", "that", "it", "i", "my", "your",
    "how", "why", "what", "when", "who", "which", "new", "just",
    "video", "watch", "official", "full", "episode", "season",
    "part", "vs", "ft", "feat", "2024", "2025", "2026",
    "subscribe", "like", "comment", "channel", "youtube",
}


@retry_with_backoff(max_retries=3)
def _fetch_trending(api_key: str, region_code: str, max_results: int = 50) -> list[dict]:
    """Fetch trending videos for a given region from YouTube Data API v3."""
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": region_code,
        "maxResults": max_results,
        "key": api_key,
    }
    response = httpx.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("items", [])


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from a string."""
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) >= 3]


def _extract_bigrams(words: list[str]) -> list[str]:
    """Generate bigrams from a word list."""
    return [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]


def _score_topics_from_videos(videos: list[dict]) -> dict[str, float]:
    """
    Score topics by weighted frequency across video titles and tags.
    Weight = view_count / 1e6 capped at 10.
    """
    topic_scores: dict[str, float] = defaultdict(float)

    for item in videos:
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})

        title = snippet.get("title", "")
        tags = snippet.get("tags", []) or []
        view_count = int(stats.get("viewCount", 0))

        # Normalize weight: cap at 10M views worth
        weight = min(view_count / 1_000_000, 10.0) + 0.1  # +0.1 so zero-view still counts

        # Keywords from title
        title_words = _extract_keywords(title)
        for bigram in _extract_bigrams(title_words):
            topic_scores[bigram] += weight * 1.5  # bigrams in titles get more weight

        for word in title_words:
            topic_scores[word] += weight * 0.5

        # Tags are high-signal — YouTube creators explicitly label these
        for tag in tags:
            tag_clean = tag.lower().strip()
            if tag_clean and tag_clean not in STOPWORDS and len(tag_clean) >= 3:
                topic_scores[tag_clean] += weight * 2.0

    return dict(topic_scores)


def collect() -> list[dict]:
    """
    Fetches trending YouTube videos across US, UK, CA regions.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, regions, region_count}.
    Fires if topic appears in 2+ regions (cross-region = stronger signal).
    signal_category: media
    """
    logger.info("Collecting YouTube trending signals...")
    results = []

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key or api_key.startswith("REPLACE"):
        logger.warning("YouTube: YOUTUBE_API_KEY not configured, skipping")
        return results

    # topic -> {region: score}
    topic_by_region: dict[str, dict[str, float]] = defaultdict(dict)

    for region in REGIONS:
        try:
            videos = _fetch_trending(api_key, region)
            region_scores = _score_topics_from_videos(videos)
            for topic, score in region_scores.items():
                topic_by_region[topic][region] = score
            logger.debug(f"YouTube: fetched {len(videos)} trending videos for {region}")
            time.sleep(1)  # Polite pacing
        except Exception as e:
            logger.warning(f"YouTube: failed to fetch trending for {region}: {e}")

    if not topic_by_region:
        logger.warning("YouTube: no data collected from any region")
        return results

    # Build per-topic aggregated scores
    topic_total: dict[str, float] = {}
    for topic, region_scores in topic_by_region.items():
        topic_total[topic] = sum(region_scores.values())

    sorted_topics = sorted(topic_total.items(), key=lambda x: x[1], reverse=True)

    # Filter to meaningful topics only (prune very low scores)
    max_score = sorted_topics[0][1] if sorted_topics else 1.0
    threshold = max_score * 0.01  # only topics with at least 1% of max score

    for topic, total_score in sorted_topics[:100]:
        if total_score < threshold:
            break

        region_scores = topic_by_region[topic]
        region_count = len(region_scores)
        regions_present = list(region_scores.keys())

        spike_score = total_score / max_score

        results.append({
            "topic": topic,
            "raw_value": round(total_score, 4),
            "baseline_value": None,  # YouTube API doesn't expose historical trending
            "spike_score": round(spike_score, 4),
            "signal_source": "youtube",
            "signal_category": "media",
            "fired": region_count >= 2,  # Cross-region = fire
            "regions": regions_present,
            "region_count": region_count,
        })

    logger.info(
        f"YouTube: {len(results)} topics extracted, "
        f"{sum(1 for r in results if r['fired'])} fired (2+ regions)"
    )
    return results
