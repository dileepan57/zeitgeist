"""
Reddit signal collector.
Primary: PRAW (official Reddit API) when credentials are available.
Fallback: RSS feeds (no auth required, titles only, no vote scores).
signal_category: community
"""
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff

load_dotenv()

# Subreddits grouped by signal type
SUBREDDITS = {
    "tech": ["technology", "programming", "MachineLearning", "artificial", "singularity",
             "LocalLLaMA", "OpenAI", "StableDiffusion", "webdev", "startups"],
    "culture": ["worldnews", "news", "todayilearned", "explainlikeimfive", "science"],
    "consumer": ["gadgets", "Android", "apple", "personalfinance", "investing",
                 "Entrepreneur", "SideProject", "Productivity"],
    "health": ["Health", "medicine", "Fitness", "mentalhealth", "nutrition"],
    "business": ["business", "Economics", "smallbusiness", "freelance"],
}

COMPLAINT_KEYWORDS = [
    "why doesn't", "why isn't there", "i can't find", "there's no app",
    "nobody has built", "frustrating", "annoying", "broken", "terrible",
    "why is there no", "i wish there was", "someone should build",
]

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can",
    "in", "on", "at", "to", "for", "of", "and", "or", "but",
    "not", "with", "this", "that", "it", "i", "my", "your",
    "how", "why", "what", "when", "who", "which", "new", "just",
    "get", "use", "using", "used", "from", "its", "out", "now",
}

ATOM_NS = "http://www.w3.org/2005/Atom"


# ---------------------------------------------------------------------------
# RSS path (no auth)
# ---------------------------------------------------------------------------

@retry_with_backoff(max_retries=3)
def _fetch_rss_posts(subreddit_name: str) -> list[dict]:
    """Fetch top weekly posts from a subreddit via RSS. No authentication required."""
    url = f"https://www.reddit.com/r/{subreddit_name}/top/.rss?t=week&limit=100"
    headers = {"User-Agent": "zeitgeist/1.0 (trend detection, non-commercial)"}
    response = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    posts = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        if title_el is not None and title_el.text:
            # RSS carries no vote score — each post weighted equally
            posts.append({
                "title": title_el.text,
                "score": 1,
                "upvote_ratio": 1.0,
            })
    return posts


def _collect_rss() -> list[dict]:
    logger.info("Collecting Reddit signals via RSS (no credentials)...")
    topic_scores: dict[str, float] = defaultdict(float)
    topic_complaint_weight: dict[str, float] = defaultdict(float)

    all_subreddits = [s for subs in SUBREDDITS.values() for s in subs]

    for subreddit_name in all_subreddits:
        try:
            posts = _fetch_rss_posts(subreddit_name)
            extracted = _extract_topics(posts)
            for phrase, score in extracted["phrase_scores"].items():
                topic_scores[phrase] += score
            for complaint in extracted["complaint_posts"]:
                topic_complaint_weight[complaint[:40]] += 10.0
            time.sleep(1)  # polite delay between subreddits
        except Exception as e:
            logger.warning(f"Reddit RSS: failed r/{subreddit_name}: {e}")

    return _build_results(topic_scores, topic_complaint_weight)


# ---------------------------------------------------------------------------
# PRAW path (OAuth credentials)
# ---------------------------------------------------------------------------

def _get_reddit():
    import praw
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "zeitgeist/1.0"),
    )


@retry_with_backoff(max_retries=3)
def _fetch_hot_posts(reddit, subreddit_name: str, limit: int = 25) -> list[dict]:
    sub = reddit.subreddit(subreddit_name)
    posts = []
    for post in sub.hot(limit=limit):
        posts.append({
            "title": post.title,
            "score": post.score,
            "num_comments": post.num_comments,
            "upvote_ratio": post.upvote_ratio,
        })
    return posts


def _collect_praw() -> list[dict]:
    logger.info("Collecting Reddit signals via PRAW...")
    topic_scores: dict[str, float] = defaultdict(float)
    topic_complaint_weight: dict[str, float] = defaultdict(float)

    try:
        reddit = _get_reddit()
    except Exception as e:
        logger.error(f"Reddit auth failed: {e}")
        return []

    for category, subreddits in SUBREDDITS.items():
        for subreddit_name in subreddits:
            try:
                posts = _fetch_hot_posts(reddit, subreddit_name)
                extracted = _extract_topics(posts)
                for phrase, score in extracted["phrase_scores"].items():
                    topic_scores[phrase] += score
                for complaint in extracted["complaint_posts"]:
                    topic_complaint_weight[complaint[:40]] += 10.0
            except Exception as e:
                logger.warning(f"Reddit PRAW: failed r/{subreddit_name}: {e}")

    return _build_results(topic_scores, topic_complaint_weight)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _extract_topics(posts: list[dict]) -> dict:
    """Extract bigrams and complaint signals from post titles."""
    word_counts: Counter = Counter()
    phrase_scores: dict[str, float] = defaultdict(float)
    complaint_posts: set[str] = set()

    for post in posts:
        title_lower = post["title"].lower()
        words = re.findall(r"\b[a-z]{3,}\b", title_lower)
        meaningful = [w for w in words if w not in STOPWORDS]
        weight = post["score"] * post.get("upvote_ratio", 1.0)

        for word in meaningful:
            word_counts[word] += weight

        for i in range(len(meaningful) - 1):
            bigram = f"{meaningful[i]} {meaningful[i + 1]}"
            phrase_scores[bigram] += weight

        for kw in COMPLAINT_KEYWORDS:
            if kw in title_lower:
                complaint_posts.add(title_lower[:80])

    return {
        "word_counts": dict(word_counts.most_common(50)),
        "phrase_scores": dict(sorted(phrase_scores.items(), key=lambda x: x[1], reverse=True)[:30]),
        "complaint_posts": list(complaint_posts),
    }


def _build_results(
    topic_scores: dict[str, float],
    topic_complaint_weight: dict[str, float],
) -> list[dict]:
    sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)[:50]
    if not sorted_topics:
        return []

    max_score = sorted_topics[0][1]
    results = []

    for topic, score in sorted_topics:
        normalized = score / max_score
        results.append({
            "topic": topic,
            "raw_value": round(score, 2),
            "baseline_value": None,
            "spike_score": round(normalized, 4),
            "signal_source": "reddit",
            "signal_category": "community",
            "fired": normalized > 0.3,
            "frustration_signal": topic in topic_complaint_weight,
        })

    logger.info(f"Reddit: {len(results)} topics, {sum(1 for r in results if r['fired'])} fired")
    return results


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def collect() -> list[dict]:
    """
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, frustration_signal}.
    Uses PRAW if REDDIT_CLIENT_ID is set, otherwise falls back to RSS.
    signal_category: community
    """
    has_credentials = bool(
        os.environ.get("REDDIT_CLIENT_ID")
        and not os.environ.get("REDDIT_CLIENT_ID", "").startswith("REPLACE")
    )

    if has_credentials:
        return _collect_praw()
    return _collect_rss()
