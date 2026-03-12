"""
Product Hunt signal collector.
Uses ProductHunt GraphQL API v2 (PRODUCTHUNT_API_KEY env var for higher limits).
Fetches today's and yesterday's top launches sorted by votes.
Fires if upvote count > 100 — high-voted launches signal validated consumer demand.
signal_category: builder
"""
import os
import re
import time
from collections import defaultdict
from datetime import date, timedelta
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

PRODUCTHUNT_GRAPHQL = "https://api.producthunt.com/v2/api/graphql"

STOPWORDS = {
    "the", "a", "an", "is", "are", "for", "and", "or", "with",
    "your", "our", "you", "that", "this", "it", "to", "of", "in",
    "on", "at", "by", "from", "not", "no", "yes", "be", "been",
    "app", "tool", "platform", "ai", "build", "built", "make",
    "get", "use", "new", "free", "best", "easy", "simple", "fast",
    "just", "via", "its", "from", "into", "more", "all", "any",
}

FETCH_DAYS_BACK = 2  # Today + yesterday

POSTS_QUERY = """
query GetPosts($postedAfter: DateTime!, $first: Int!, $after: String) {
  posts(postedAfter: $postedAfter, first: $first, after: $after,
        order: VOTES) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        name
        tagline
        description
        votesCount
        commentsCount
        topics {
          edges {
            node {
              name
              slug
            }
          }
        }
        url
        website
        createdAt
      }
    }
  }
}
"""


@retry_with_backoff(max_retries=3)
def _fetch_posts(api_token: str | None, posted_after: str, cursor: str | None = None) -> dict:
    """
    Fetch Product Hunt posts sorted by votes, paginated.
    Uses developer token if available, otherwise anonymous (lower rate limit).
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Host": "api.producthunt.com",
        "User-Agent": "zeitgeist/1.0",
    }
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    variables = {
        "postedAfter": posted_after,
        "first": 50,
    }
    if cursor:
        variables["after"] = cursor

    payload = {"query": POSTS_QUERY, "variables": variables}

    response = httpx.post(PRODUCTHUNT_GRAPHQL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def _extract_topics_from_product(name: str, tagline: str, description: str) -> list[str]:
    """
    Extract topic keywords from product name, tagline, and description.
    Returns list of meaningful keyword phrases.
    """
    text = f"{name} {tagline} {description or ''}"
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", text.lower())
    filtered = [w for w in words if w not in STOPWORDS and len(w) >= 3]

    topics = list(set(filtered))

    # Bigrams from tagline (highest signal)
    tagline_words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", tagline.lower())
    tagline_filtered = [w for w in tagline_words if w not in STOPWORDS]
    for i in range(len(tagline_filtered) - 1):
        bigram = f"{tagline_filtered[i]} {tagline_filtered[i+1]}"
        topics.append(bigram)

    return topics


def collect() -> list[dict]:
    """
    Fetches ProductHunt top launches from last 2 days.
    Groups by product topics (both PH taxonomy topics and extracted keywords).
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, upvote_count,
                     product_count, top_products}.
    Fires if upvote count > 100 for a topic.
    signal_category: builder
    """
    logger.info("Collecting ProductHunt signals...")
    results = []

    api_token = os.environ.get("PRODUCTHUNT_API_KEY") or os.environ.get("PRODUCTHUNT_TOKEN")

    # Fetch posts from last FETCH_DAYS_BACK days
    cutoff_date = (date.today() - timedelta(days=FETCH_DAYS_BACK)).isoformat() + "T00:00:00Z"

    all_posts = []
    cursor = None
    max_pages = 5

    for page in range(max_pages):
        try:
            data = _fetch_posts(api_token, cutoff_date, cursor)

            errors = data.get("errors")
            if errors:
                logger.warning(f"ProductHunt GraphQL errors: {errors}")
                break

            posts_data = data.get("data", {}).get("posts", {})
            edges = posts_data.get("edges", [])
            page_info = posts_data.get("pageInfo", {})

            for edge in edges:
                node = edge.get("node", {})
                all_posts.append(node)

            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

            logger.debug(f"ProductHunt: page {page + 1}, {len(edges)} posts")

            if not has_next or not cursor:
                break

            time.sleep(1)

        except Exception as e:
            logger.warning(f"ProductHunt: fetch failed on page {page + 1}: {e}")
            break

    if not all_posts:
        logger.warning("ProductHunt: no posts collected")
        return results

    logger.debug(f"ProductHunt: {len(all_posts)} posts fetched total")

    # --- Process individual high-vote products as direct signals ---
    for post in all_posts:
        votes = post.get("votesCount", 0)
        name = post.get("name", "")
        tagline = post.get("tagline", "")

        if votes > 100:  # Direct fire condition
            ph_topics = [
                edge["node"]["name"]
                for edge in post.get("topics", {}).get("edges", [])
            ]
            extracted_topics = _extract_topics_from_product(
                name, tagline, post.get("description", "") or ""
            )

            results.append({
                "topic": name.lower(),
                "raw_value": votes,
                "baseline_value": 100,  # Fire threshold
                "spike_score": round(min(votes / 500.0, 1.0), 4),
                "signal_source": "producthunt",
                "signal_category": "builder",
                "fired": True,
                "upvote_count": votes,
                "product_count": 1,
                "product_name": name,
                "tagline": tagline,
                "ph_topics": ph_topics,
                "extracted_topics": extracted_topics[:8],
                "comments_count": post.get("commentsCount", 0),
                "url": post.get("url", ""),
            })

    # --- Aggregate by ProductHunt taxonomy topics ---
    topic_votes: dict[str, int] = defaultdict(int)
    topic_products: dict[str, list[str]] = defaultdict(list)
    topic_product_count: dict[str, int] = defaultdict(int)

    for post in all_posts:
        votes = post.get("votesCount", 0)
        name = post.get("name", "")

        ph_topics = [
            edge["node"]["name"]
            for edge in post.get("topics", {}).get("edges", [])
        ]

        for topic in ph_topics:
            topic_votes[topic] += votes
            topic_product_count[topic] += 1
            if len(topic_products[topic]) < 3:
                topic_products[topic].append(f"{name} ({votes} votes)")

    if topic_votes:
        max_votes = max(topic_votes.values())
        for topic, total_votes in sorted(topic_votes.items(), key=lambda x: x[1], reverse=True)[:40]:
            spike_score = total_votes / max_votes if max_votes > 0 else 0.0
            results.append({
                "topic": f"ph_topic:{topic.lower()}",
                "raw_value": total_votes,
                "baseline_value": None,
                "spike_score": round(spike_score, 4),
                "signal_source": "producthunt",
                "signal_category": "builder",
                "fired": total_votes > 100,
                "upvote_count": total_votes,
                "product_count": topic_product_count[topic],
                "top_products": topic_products[topic],
            })

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(f"ProductHunt: {len(results)} signals, {fired_count} fired (>100 upvotes)")
    return results
