"""
Podcast signal collector (iTunes + Listen Notes).
Uses iTunes Search API (free, no key) to find podcasts about trending topics.
Also uses Listen Notes free tier if LISTEN_NOTES_KEY is available.
Podcast creation surge around a topic = thought leaders are pivoting = media signal.
signal_category: media
"""
import os
import re
import time
from collections import defaultdict
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

ITUNES_SEARCH_API = "https://itunes.apple.com/search"
LISTEN_NOTES_API = "https://listen-api.listennotes.com/api/v2"

# Topics to probe for podcast activity
PODCAST_TOPICS = [
    # AI & Technology
    "artificial intelligence podcast",
    "large language model",
    "AI startup",
    "machine learning podcast",
    "generative AI",
    "AI safety",
    "AI agents",
    # Science & Health
    "longevity science",
    "biohacking podcast",
    "psychedelic research",
    "microbiome health",
    "precision medicine",
    "mental health tech",
    # Business & Finance
    "venture capital podcast",
    "startup founder podcast",
    "DeFi crypto podcast",
    "climate tech investing",
    "creator economy",
    # Culture & Society
    "future of work podcast",
    "remote work podcast",
    "digital nomad",
    "conscious capitalism",
    # Emerging Areas
    "quantum computing",
    "synthetic biology podcast",
    "space exploration podcast",
    "robotics podcast",
    "augmented reality",
    "web3 podcast",
    "climate change solutions",
]

# Countries to search (iTunes is region-specific)
COUNTRIES = ["us", "gb", "ca", "au"]


@retry_with_backoff(max_retries=3)
def _search_podcasts_itunes(term: str, country: str = "us", limit: int = 25) -> list[dict]:
    """
    Search iTunes for podcasts matching a term.
    Returns list of podcast result dicts.
    """
    params = {
        "term": term,
        "country": country,
        "media": "podcast",
        "entity": "podcast",
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
    return response.json().get("results", [])


@retry_with_backoff(max_retries=3)
def _search_listen_notes(api_key: str, query: str, sort_by: int = 1) -> dict:
    """
    Search Listen Notes for podcasts.
    sort_by: 0=relevance, 1=recent (we want recent to detect new shows)
    """
    headers = {
        "X-ListenAPI-Key": api_key,
        "User-Agent": "zeitgeist/1.0",
    }
    params = {
        "q": query,
        "sort_by_date": sort_by,
        "type": "podcast",
        "language": "English",
        "len_min": 10,
    }

    response = httpx.get(
        f"{LISTEN_NOTES_API}/search",
        headers=headers,
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


@retry_with_backoff(max_retries=3)
def _fetch_listen_notes_trending(api_key: str) -> dict:
    """
    Fetch Listen Notes trending podcasts.
    """
    headers = {
        "X-ListenAPI-Key": api_key,
        "User-Agent": "zeitgeist/1.0",
    }
    response = httpx.get(
        f"{LISTEN_NOTES_API}/trending",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _compute_podcast_metrics(podcasts: list[dict]) -> dict:
    """Compute aggregate metrics from podcast results."""
    if not podcasts:
        return {
            "count": 0,
            "avg_episode_count": 0.0,
            "avg_rating": 0.0,
            "total_review_count": 0,
            "top_podcasts": [],
        }

    episode_counts = [
        p.get("trackCount", 0)
        for p in podcasts
        if p.get("trackCount")
    ]
    ratings = [
        p.get("averageUserRating", 0.0)
        for p in podcasts
        if p.get("averageUserRating")
    ]
    review_counts = [
        p.get("userRatingCount", 0)
        for p in podcasts
        if p.get("userRatingCount")
    ]

    top_podcasts = []
    for p in sorted(podcasts, key=lambda x: x.get("userRatingCount", 0), reverse=True)[:3]:
        top_podcasts.append({
            "name": p.get("collectionName", ""),
            "episodes": p.get("trackCount", 0),
            "rating": p.get("averageUserRating", 0),
            "artist": p.get("artistName", ""),
        })

    return {
        "count": len(podcasts),
        "avg_episode_count": round(sum(episode_counts) / len(episode_counts), 1) if episode_counts else 0.0,
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
        "total_review_count": sum(review_counts),
        "top_podcasts": top_podcasts,
    }


def collect() -> list[dict]:
    """
    Searches iTunes for podcasts and episodes about trending topics.
    Also uses Listen Notes if LISTEN_NOTES_KEY is available.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, podcast_count,
                     avg_rating, top_podcasts}.
    Fires if podcast_count >= 5 (multiple shows = emerging media category).
    signal_category: media
    """
    logger.info("Collecting podcast (iTunes/Listen Notes) signals...")
    results = []

    listen_notes_key = os.environ.get("LISTEN_NOTES_KEY")

    # --- iTunes Podcast Signals ---
    topic_metrics: dict[str, dict] = {}

    for topic in PODCAST_TOPICS:
        try:
            podcasts = _search_podcasts_itunes(topic, country="us", limit=20)
            metrics = _compute_podcast_metrics(podcasts)
            topic_metrics[topic] = metrics

            logger.debug(
                f"iTunes podcasts '{topic}': {metrics['count']} results, "
                f"avg_rating={metrics['avg_rating']}"
            )

            time.sleep(1.5)  # iTunes rate limit

        except Exception as e:
            logger.warning(f"iTunes: failed for podcast topic '{topic}': {e}")
            time.sleep(2)

    # Normalize and build results
    if topic_metrics:
        max_count = max(m["count"] for m in topic_metrics.values()) if topic_metrics else 1

        for topic, metrics in topic_metrics.items():
            count = metrics["count"]
            avg_rating = metrics["avg_rating"]
            total_reviews = metrics["total_review_count"]

            # Spike score: combination of podcast count and engagement
            base_score = count / max_count if max_count > 0 else 0.0
            engagement_boost = min(total_reviews / 10000.0, 0.2)
            spike_score = min(base_score + engagement_boost, 1.0)

            fired = count >= 5

            results.append({
                "topic": topic,
                "raw_value": count,
                "baseline_value": 5.0,  # Threshold for "active media category"
                "spike_score": round(spike_score, 4),
                "signal_source": "itunes_podcasts",
                "signal_category": "media",
                "fired": fired,
                "podcast_count": count,
                "avg_episode_count": metrics["avg_episode_count"],
                "avg_rating": avg_rating,
                "total_review_count": total_reviews,
                "top_podcasts": metrics["top_podcasts"],
            })

    # --- Listen Notes Signals (if API key available) ---
    if listen_notes_key:
        try:
            trending_data = _fetch_listen_notes_trending(listen_notes_key)
            trending_podcasts = trending_data.get("podcasts", [])

            if trending_podcasts:
                STOPWORDS = {
                    "podcast", "show", "episode", "weekly", "daily",
                    "the", "a", "an", "and", "or", "for", "with",
                    "your", "our", "about", "from", "new", "best",
                }
                trend_topic_count: dict[str, int] = defaultdict(int)
                trend_topic_shows: dict[str, list] = defaultdict(list)

                for podcast in trending_podcasts:
                    title = podcast.get("title", "") or podcast.get("title_original", "") or ""
                    description = podcast.get("description", "") or podcast.get("description_original", "") or ""

                    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{3,}\b", f"{title} {description}".lower())
                    filtered = [w for w in words if w not in STOPWORDS]

                    for w in filtered:
                        trend_topic_count[w] += 1
                    for i in range(len(filtered) - 1):
                        bigram = f"{filtered[i]} {filtered[i+1]}"
                        if len(bigram) >= 8:
                            trend_topic_count[bigram] += 1

                if trend_topic_count:
                    max_t = max(trend_topic_count.values())
                    for topic, count in sorted(
                        trend_topic_count.items(), key=lambda x: x[1], reverse=True
                    )[:30]:
                        results.append({
                            "topic": f"ln:{topic}",
                            "raw_value": count,
                            "baseline_value": None,
                            "spike_score": round(count / max_t, 4),
                            "signal_source": "listen_notes",
                            "signal_category": "media",
                            "fired": count >= 3,
                            "podcast_count": count,
                            "source": "listen_notes_trending",
                        })

            logger.debug(f"Listen Notes: {len(trending_podcasts)} trending podcasts processed")
            time.sleep(2)

        except Exception as e:
            logger.warning(f"Listen Notes: failed to fetch trending: {e}")

        # Also search for specific topics via Listen Notes
        for topic in PODCAST_TOPICS[:10]:  # Limit to avoid rate limits
            try:
                data = _search_listen_notes(listen_notes_key, topic, sort_by=1)
                count = data.get("total", 0)
                podcasts = data.get("results", [])

                results.append({
                    "topic": f"ln_search:{topic}",
                    "raw_value": count,
                    "baseline_value": None,
                    "spike_score": round(min(count / 1000.0, 1.0), 4),
                    "signal_source": "listen_notes",
                    "signal_category": "media",
                    "fired": count >= 10,
                    "podcast_count": count,
                    "top_podcasts": [
                        p.get("title_original", "") or p.get("title", "")
                        for p in podcasts[:3]
                    ],
                })

                time.sleep(1.5)

            except Exception as e:
                logger.debug(f"Listen Notes search failed for '{topic}': {e}")

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(
        f"Podcasts: {len(results)} topic signals, {fired_count} fired"
    )
    return results
