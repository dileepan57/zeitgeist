"""
Stack Exchange API signal collector.
Uses the free Stack Exchange API v2.3 (no key required for basic use).
Fetches questions from the last 7 days with vote_count > 5,
groups by tags to identify emerging technology topics.
signal_category: community
"""
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

STACK_API_BASE = "https://api.stackexchange.com/2.3"

# Sites to monitor — SO + specialized sites for emerging tech
SITES = [
    "stackoverflow",
    "datascience",
    "ai",
    "softwareengineering",
    "devops",
    "crypto",
    "bioinformatics",
]

# We'll track questions with >= this vote threshold
MIN_VOTES = 5

# Tags that are "baseline" / always-present — exclude from spike detection
BASELINE_TAGS = {
    "python", "javascript", "java", "c#", "html", "css", "sql",
    "php", "c++", "typescript", "node.js", "react", "angular",
    "vue.js", "git", "linux", "docker", "android", "ios",
    "arrays", "string", "list", "function", "class", "object",
    "json", "api", "rest", "http", "database", "mysql",
    "postgresql", "mongodb", "regex", "bash", "shell",
}


@retry_with_backoff(max_retries=3)
def _fetch_questions(site: str, from_date: int, min_votes: int = MIN_VOTES, page: int = 1) -> dict:
    """
    Fetch questions from a Stack Exchange site newer than from_date (unix timestamp),
    with vote_count above min_votes.
    """
    params = {
        "site": site,
        "fromdate": from_date,
        "min": min_votes,
        "sort": "votes",
        "order": "desc",
        "filter": "!T1gn.fZ3DaFfEDIBNJ",  # includes tags, score, answer_count, view_count
        "pagesize": 100,
        "page": page,
    }
    response = httpx.get(f"{STACK_API_BASE}/questions", params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    # Log remaining quota
    quota = data.get("quota_remaining", "?")
    logger.debug(f"Stack Exchange API quota remaining: {quota}")

    return data


@retry_with_backoff(max_retries=3)
def _fetch_tag_info(tags: list[str], site: str = "stackoverflow") -> dict[str, dict]:
    """
    Fetch tag statistics (question count, etc.) for a list of tags.
    Used for baseline comparison.
    """
    tag_str = ";".join(tags[:20])  # API limit
    params = {
        "site": site,
        "filter": "!9_bDE(gge",  # includes count, is_required, has_synonyms
        "inname": None,  # skip inname filter
        "page": 1,
        "pagesize": 20,
    }
    # Build comma-separated tag query
    url = f"{STACK_API_BASE}/tags/{tag_str}/info"
    response = httpx.get(url, params=params, timeout=30)
    response.raise_for_status()
    items = response.json().get("items", [])
    return {item["name"]: item for item in items}


def collect() -> list[dict]:
    """
    Fetches Stack Overflow/Exchange questions from last 7 days with votes > 5.
    Groups by tags to find emerging technology topics.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, question_count,
                     avg_votes, avg_views, sites}.
    signal_category: community
    """
    logger.info("Collecting Stack Overflow/Exchange signals...")
    results = []

    # Unix timestamp for 7 days ago
    week_ago = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())

    # tag -> aggregated metrics across sites
    tag_metrics: dict[str, dict] = defaultdict(lambda: {
        "question_count": 0,
        "total_votes": 0,
        "total_views": 0,
        "sites": set(),
        "questions": [],
    })

    for site in SITES:
        try:
            page = 1
            has_more = True
            site_question_count = 0

            while has_more and page <= 3:  # cap at 3 pages per site
                data = _fetch_questions(site, from_date=week_ago, page=page)
                questions = data.get("items", [])
                has_more = data.get("has_more", False)

                for q in questions:
                    tags = q.get("tags", [])
                    score = q.get("score", 0)
                    views = q.get("view_count", 0)
                    title = q.get("title", "")

                    for tag in tags:
                        if tag in BASELINE_TAGS:
                            continue
                        tag_metrics[tag]["question_count"] += 1
                        tag_metrics[tag]["total_votes"] += score
                        tag_metrics[tag]["total_views"] += views
                        tag_metrics[tag]["sites"].add(site)
                        if len(tag_metrics[tag]["questions"]) < 3:
                            tag_metrics[tag]["questions"].append(title[:100])

                site_question_count += len(questions)
                page += 1
                time.sleep(1)  # Stack Exchange asks for <30 req/s, be safe

            logger.debug(f"Stack Exchange {site}: {site_question_count} questions (7d, votes>{MIN_VOTES})")

        except Exception as e:
            logger.warning(f"Stack Exchange: failed for site {site}: {e}")

        time.sleep(2)

    if not tag_metrics:
        logger.warning("Stack Exchange: no tag data collected")
        return results

    # Score tags by question_count as the primary metric
    # Sort by question count descending
    sorted_tags = sorted(
        tag_metrics.items(),
        key=lambda x: x[1]["question_count"],
        reverse=True
    )[:80]

    if not sorted_tags:
        return results

    max_count = sorted_tags[0][1]["question_count"]

    for tag, metrics in sorted_tags:
        qcount = metrics["question_count"]
        total_votes = metrics["total_votes"]
        total_views = metrics["total_views"]
        sites_list = list(metrics["sites"])

        avg_votes = total_votes / qcount if qcount > 0 else 0
        avg_views = total_views / qcount if qcount > 0 else 0

        # Spike score is question count relative to the top tag
        spike_score = qcount / max_count

        # Fires if significant absolute count AND relatively high score
        fired = qcount >= 3 and spike_score >= 0.05

        results.append({
            "topic": tag,
            "raw_value": qcount,
            "baseline_value": None,  # Would need historical data store for true baseline
            "spike_score": round(spike_score, 4),
            "signal_source": "stackoverflow",
            "signal_category": "community",
            "fired": fired,
            "question_count": qcount,
            "avg_votes": round(avg_votes, 2),
            "avg_views": round(avg_views, 0),
            "sites": sites_list,
            "sample_questions": metrics["questions"],
        })

    logger.info(
        f"Stack Exchange: {len(results)} tags extracted, "
        f"{sum(1 for r in results if r['fired'])} fired"
    )
    return results
