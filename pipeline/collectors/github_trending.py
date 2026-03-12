"""
GitHub Trending collector.
Uses GitHub API (free, 60 req/hr unauth, 5000/hr with token).
Tracks trending repos, star velocity, and topic/language clustering.
This is an EARLY signal — 6-18 months ahead of mainstream.
"""
import os
import httpx
from datetime import date, timedelta
from collections import defaultdict
from loguru import logger
from dotenv import load_dotenv
from pipeline.utils.rate_limiter import retry_with_backoff

load_dotenv()

GITHUB_API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "zeitgeist/1.0",
}
if token := os.environ.get("GITHUB_TOKEN"):
    HEADERS["Authorization"] = f"Bearer {token}"

TOPIC_CATEGORIES = [
    "machine-learning", "artificial-intelligence", "large-language-models",
    "computer-vision", "robotics", "web3", "blockchain", "defi",
    "climate-tech", "biotech", "health-tech", "fintech", "edtech",
    "developer-tools", "productivity", "automation", "no-code",
]


@retry_with_backoff(max_retries=3)
def _search_repos(query: str, sort: str = "stars", days: int = 7) -> list[dict]:
    """Search repos created/updated in the last N days."""
    since = (date.today() - timedelta(days=days)).isoformat()
    params = {
        "q": f"{query} created:>{since}",
        "sort": sort,
        "order": "desc",
        "per_page": 30,
    }
    response = httpx.get(f"{GITHUB_API}/search/repositories", headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("items", [])


@retry_with_backoff(max_retries=3)
def _get_trending_topics() -> list[dict]:
    """Scrape GitHub trending page topics via API explore."""
    # GitHub doesn't have an official trending API, so we use search
    # with high star velocity as a proxy
    since = (date.today() - timedelta(days=7)).isoformat()
    params = {
        "q": f"stars:>50 created:>{since}",
        "sort": "stars",
        "order": "desc",
        "per_page": 50,
    }
    response = httpx.get(f"{GITHUB_API}/search/repositories", headers=HEADERS, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("items", [])


def _extract_topic_signals(repos: list[dict]) -> dict[str, dict]:
    """Extract topics and themes from repo metadata."""
    topic_scores: dict[str, float] = defaultdict(float)
    topic_repos: dict[str, list[str]] = defaultdict(list)

    for repo in repos:
        stars = repo.get("stargazers_count", 0)
        topics = repo.get("topics", [])
        description = repo.get("description", "") or ""
        name = repo.get("name", "")
        language = repo.get("language", "") or ""

        # Weight by star velocity (stars in 7 days is high signal)
        weight = min(stars / 100, 10.0)

        for topic in topics:
            topic_scores[topic] += weight
            topic_repos[topic].append(f"{repo['full_name']} ({stars}⭐)")

        # Extract from description (simple keyword extraction)
        if description:
            words = description.lower().split()
            for i in range(len(words) - 1):
                bigram = f"{words[i]} {words[i+1]}"
                if len(bigram) > 8 and all(len(w) > 3 for w in [words[i], words[i+1]]):
                    topic_scores[bigram] += weight * 0.3

    return {
        topic: {
            "score": score,
            "repos": topic_repos.get(topic, [])[:5],
        }
        for topic, score in topic_scores.items()
        if score >= 1.0
    }


def collect() -> list[dict]:
    """
    Returns list of {topic, raw_value, spike_score, signal_source, signal_category}
    GitHub is a BUILDER signal — earliest leading indicator.
    """
    logger.info("Collecting GitHub Trending signals...")
    results = []

    all_repos = []

    # Trending by overall stars
    try:
        trending = _get_trending_topics()
        all_repos.extend(trending)
    except Exception as e:
        logger.warning(f"GitHub: general trending fetch failed: {e}")

    # Trending by specific topics (builder signal categories)
    for topic in TOPIC_CATEGORIES[:8]:  # Limit to avoid rate limits
        try:
            repos = _search_repos(f"topic:{topic}", days=7)
            all_repos.extend(repos)
        except Exception as e:
            logger.warning(f"GitHub: topic search failed for {topic}: {e}")

    if not all_repos:
        return results

    topic_signals = _extract_topic_signals(all_repos)
    sorted_topics = sorted(topic_signals.items(), key=lambda x: x[1]["score"], reverse=True)[:50]

    if not sorted_topics:
        return results

    max_score = sorted_topics[0][1]["score"]

    for topic, data in sorted_topics:
        normalized = data["score"] / max_score
        results.append({
            "topic": topic,
            "raw_value": round(data["score"], 2),
            "baseline_value": None,
            "spike_score": round(normalized, 4),
            "signal_source": "github_trending",
            "signal_category": "builder",
            "fired": normalized > 0.15,
            "repos": data["repos"],
        })

    logger.info(f"GitHub: {len(results)} topics, {sum(1 for r in results if r['fired'])} fired")
    return results
