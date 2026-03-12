"""
Reddit signal collector.
Uses PRAW (official Reddit API, free OAuth).
Monitors hot posts across high-signal subreddits and tracks emerging topics.
"""
import os
import praw
from collections import defaultdict
from loguru import logger
from dotenv import load_dotenv
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


def _get_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "zeitgeist/1.0"),
    )


@retry_with_backoff(max_retries=3)
def _fetch_hot_posts(reddit: praw.Reddit, subreddit_name: str, limit: int = 25) -> list[dict]:
    sub = reddit.subreddit(subreddit_name)
    posts = []
    for post in sub.hot(limit=limit):
        posts.append({
            "title": post.title,
            "score": post.score,
            "num_comments": post.num_comments,
            "upvote_ratio": post.upvote_ratio,
            "url": post.url,
        })
    return posts


def _extract_topics(posts: list[dict]) -> dict[str, dict]:
    """Simple keyword frequency extraction from post titles."""
    from collections import Counter
    import re

    word_counts: Counter = Counter()
    phrase_scores: dict[str, float] = defaultdict(float)
    complaint_topics: set[str] = set()

    stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                 "have", "has", "had", "do", "does", "did", "will", "would",
                 "could", "should", "may", "might", "must", "shall", "can",
                 "in", "on", "at", "to", "for", "of", "and", "or", "but",
                 "not", "with", "this", "that", "it", "i", "my", "your",
                 "how", "why", "what", "when", "who", "which", "new", "just"}

    for post in posts:
        title_lower = post["title"].lower()
        words = re.findall(r"\b[a-z]{3,}\b", title_lower)
        meaningful = [w for w in words if w not in stopwords]
        weight = post["score"] * post["upvote_ratio"]

        # Single word tracking
        for word in meaningful:
            word_counts[word] += weight

        # Bigrams
        for i in range(len(meaningful) - 1):
            bigram = f"{meaningful[i]} {meaningful[i+1]}"
            phrase_scores[bigram] += weight

        # Complaint detection
        for kw in COMPLAINT_KEYWORDS:
            if kw in title_lower:
                complaint_topics.add(title_lower[:80])

    return {
        "word_counts": dict(word_counts.most_common(50)),
        "phrase_scores": dict(sorted(phrase_scores.items(), key=lambda x: x[1], reverse=True)[:30]),
        "complaint_posts": list(complaint_topics),
    }


def collect() -> list[dict]:
    """
    Returns list of {topic, raw_value, baseline_value, spike_score, signal_source, signal_category}
    """
    logger.info("Collecting Reddit signals...")
    results = []

    try:
        reddit = _get_reddit()
    except Exception as e:
        logger.error(f"Reddit auth failed: {e}")
        return results

    topic_scores: dict[str, float] = defaultdict(float)
    topic_complaint_weight: dict[str, float] = defaultdict(float)

    for category, subreddits in SUBREDDITS.items():
        for subreddit_name in subreddits:
            try:
                posts = _fetch_hot_posts(reddit, subreddit_name)
                extracted = _extract_topics(posts)

                # Weight phrases higher than single words
                for phrase, score in extracted["phrase_scores"].items():
                    topic_scores[phrase] += score

                # Add complaint weight to relevant topics
                for complaint in extracted["complaint_posts"]:
                    topic_complaint_weight[complaint[:40]] += 10.0

            except Exception as e:
                logger.warning(f"Reddit: failed to fetch r/{subreddit_name}: {e}")

    # Convert to signal format — use top topics by score
    sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)[:50]

    if not sorted_topics:
        return results

    max_score = sorted_topics[0][1]

    for topic, score in sorted_topics:
        normalized = score / max_score
        results.append({
            "topic": topic,
            "raw_value": round(score, 2),
            "baseline_value": None,  # Reddit doesn't provide historical baseline easily
            "spike_score": round(normalized, 4),
            "signal_source": "reddit",
            "signal_category": "community",
            "fired": normalized > 0.3,
            "frustration_signal": topic in topic_complaint_weight,
        })

    logger.info(f"Reddit: {len(results)} topics, {sum(1 for r in results if r['fired'])} fired")
    return results
