"""
Substack newsletter signal collector.
Scrapes Substack leaderboard and trending posts to identify rising newsletter topics.
Newsletters aggregate expert opinion — when new niches appear, they precede mass media.
signal_category: media
"""
import re
import time
from collections import defaultdict
from loguru import logger
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

SUBSTACK_BASE = "https://substack.com"

# Substack leaderboard and discovery pages
SUBSTACK_PAGES = [
    ("trending", "https://substack.com/top"),
    ("technology", "https://substack.com/top/technology"),
    ("science", "https://substack.com/top/science"),
    ("health", "https://substack.com/top/health"),
    ("culture", "https://substack.com/top/culture"),
    ("business", "https://substack.com/top/business"),
    ("finance", "https://substack.com/top/finance"),
    ("politics", "https://substack.com/top/politics"),
]

# Also try Substack's API endpoint for recommendations
SUBSTACK_RECOMMENDATIONS_API = "https://substack.com/api/v1/leaderboard"
SUBSTACK_TRENDING_POSTS_API = "https://substack.com/api/v1/trending"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

API_HEADERS = {
    "User-Agent": "zeitgeist/1.0",
    "Accept": "application/json",
}

STOPWORDS = {
    "the", "a", "an", "for", "and", "or", "with", "your", "our",
    "you", "that", "this", "it", "to", "of", "in", "on", "at",
    "by", "from", "not", "no", "yes", "be", "been", "newsletter",
    "substack", "weekly", "daily", "monthly", "subscribe", "issue",
    "note", "notes", "letter", "letters", "post", "posts", "read",
    "reading", "write", "writing", "written", "by", "about", "top",
    "new", "get", "how", "why", "what", "when", "who", "which",
}


@retry_with_backoff(max_retries=3)
def _fetch_leaderboard_api(category: str = "", limit: int = 50) -> list[dict]:
    """
    Attempt to fetch Substack leaderboard via internal API.
    Returns list of newsletter dicts.
    """
    params = {
        "limit": limit,
        "fresh": "true",
    }
    if category:
        params["category"] = category

    response = httpx.get(
        SUBSTACK_RECOMMENDATIONS_API,
        params=params,
        headers=API_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    # Response shape varies — try multiple keys
    newsletters = (
        data if isinstance(data, list) else
        data.get("results", []) or
        data.get("publications", []) or
        data.get("items", []) or
        []
    )
    return newsletters


@retry_with_backoff(max_retries=3)
def _scrape_substack_top(url: str) -> list[dict]:
    """
    Scrape a Substack /top or /top/category page.
    Returns list of newsletter dicts.
    """
    response = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    newsletters = []

    # Substack leaderboard items
    items = (
        soup.select(".publication-card") or
        soup.select("[class*='publication-card']") or
        soup.select(".reader2-hero-card") or
        soup.select("[class*='LeaderboardCard']") or
        soup.select("div[class*='card']") or
        []
    )

    # Fallback: look for headings + descriptions
    if not items:
        items = soup.find_all("article")
        if not items:
            # Try finding structured links
            links = soup.find_all("a", href=re.compile(r"substack\.com"))
            for link in links[:30]:
                text = link.get_text(strip=True)
                if len(text) > 5:
                    newsletters.append({
                        "name": text,
                        "tagline": "",
                        "category": "",
                        "subscriber_count": 0,
                        "url": link.get("href", ""),
                    })
            return newsletters

    for item in items[:40]:
        try:
            # Name
            name_el = (
                item.find(class_=re.compile(r"name|title|publication", re.I)) or
                item.find("h2") or
                item.find("h3") or
                item.find("strong")
            )
            name = name_el.get_text(strip=True) if name_el else ""

            # Tagline / description
            desc_el = (
                item.find(class_=re.compile(r"tagline|desc|subtitle|summary", re.I)) or
                item.find("p")
            )
            tagline = desc_el.get_text(strip=True)[:300] if desc_el else ""

            # Category
            cat_el = item.find(class_=re.compile(r"category|tag|genre", re.I))
            category = cat_el.get_text(strip=True) if cat_el else ""

            # Subscriber count (not always visible)
            sub_text = item.get_text(" ", strip=True)
            sub_match = re.search(r"([\d,]+)\s*(subscribers?|readers?|followers?)", sub_text, re.I)
            subscriber_count = 0
            if sub_match:
                subscriber_count = int(sub_match.group(1).replace(",", ""))

            # URL
            link_el = item.find("a", href=True)
            url = link_el.get("href", "") if link_el else ""

            if name:
                newsletters.append({
                    "name": name,
                    "tagline": tagline,
                    "category": category,
                    "subscriber_count": subscriber_count,
                    "url": url,
                })

        except Exception as e:
            logger.debug(f"Substack: failed to parse newsletter card: {e}")
            continue

    return newsletters


def _extract_topics(name: str, tagline: str, category: str) -> list[str]:
    """Extract topic keywords from newsletter metadata."""
    topics = []

    # Category is explicit — high signal
    if category and category.lower() not in STOPWORDS:
        topics.append(category.lower().strip())

    # Bigrams from name
    name_words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", name.lower())
    name_filtered = [w for w in name_words if w not in STOPWORDS]
    for w in name_filtered:
        topics.append(w)
    for i in range(len(name_filtered) - 1):
        topics.append(f"{name_filtered[i]} {name_filtered[i+1]}")

    # Keywords from tagline
    tagline_words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", tagline.lower())
    tagline_filtered = [w for w in tagline_words if w not in STOPWORDS]
    for i in range(len(tagline_filtered) - 1):
        bigram = f"{tagline_filtered[i]} {tagline_filtered[i+1]}"
        if len(bigram) >= 8:
            topics.append(bigram)

    return list(set(topics))


def collect() -> list[dict]:
    """
    Scrapes Substack leaderboard pages to extract trending newsletter topics.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, newsletter_count,
                     avg_subscribers, sample_newsletters}.
    Fires if topic appears across multiple newsletters or has high subscriber reach.
    signal_category: media
    """
    logger.info("Collecting Substack newsletter signals...")
    results = []

    all_newsletters = []

    # Try the Substack API first (cleaner data)
    try:
        api_newsletters = _fetch_leaderboard_api()
        if api_newsletters:
            for item in api_newsletters:
                name = (
                    item.get("name", "") or
                    item.get("title", "") or
                    item.get("publication_name", "") or ""
                )
                tagline = (
                    item.get("description", "") or
                    item.get("subtitle", "") or ""
                )
                category = item.get("category", "") or item.get("type", "") or ""
                subscriber_count = (
                    item.get("free_subscriber_count", 0) or
                    item.get("subscriber_count", 0) or 0
                )
                url = item.get("base_url", "") or item.get("url", "") or ""

                if name:
                    all_newsletters.append({
                        "name": name,
                        "tagline": tagline[:300],
                        "category": category,
                        "subscriber_count": int(subscriber_count),
                        "url": url,
                    })

        logger.debug(f"Substack API: {len(all_newsletters)} newsletters")
        time.sleep(2)

    except Exception as e:
        logger.debug(f"Substack API failed: {e}. Falling back to scraping.")

    # Scrape each category page
    for page_name, url in SUBSTACK_PAGES:
        try:
            newsletters = _scrape_substack_top(url)
            all_newsletters.extend(newsletters)
            logger.debug(f"Substack [{page_name}]: {len(newsletters)} newsletters")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Substack: failed to scrape {page_name}: {e}")
            time.sleep(3)

    if not all_newsletters:
        logger.warning("Substack: no newsletters collected")
        return results

    logger.debug(f"Substack: {len(all_newsletters)} total newsletters collected")

    # Aggregate by topic
    topic_newsletter_count: dict[str, int] = defaultdict(int)
    topic_subscribers: dict[str, list[int]] = defaultdict(list)
    topic_newsletter_names: dict[str, list[str]] = defaultdict(list)

    for nl in all_newsletters:
        topics = _extract_topics(nl["name"], nl["tagline"], nl["category"])
        sub_count = nl["subscriber_count"]

        for topic in topics:
            topic_newsletter_count[topic] += 1
            if sub_count > 0:
                topic_subscribers[topic].append(sub_count)
            if len(topic_newsletter_names[topic]) < 5:
                topic_newsletter_names[topic].append(nl["name"])

    if not topic_newsletter_count:
        logger.warning("Substack: no topics extracted")
        return results

    max_count = max(topic_newsletter_count.values())

    for topic, count in sorted(
        topic_newsletter_count.items(), key=lambda x: x[1], reverse=True
    )[:80]:
        sub_list = topic_subscribers.get(topic, [])
        avg_subs = sum(sub_list) / len(sub_list) if sub_list else 0
        total_subs = sum(sub_list)

        spike_score = count / max_count if max_count > 0 else 0.0

        # Fire if topic spans multiple newsletters OR has very high subscriber reach
        fired = count >= 2 or total_subs >= 50_000

        results.append({
            "topic": topic,
            "raw_value": count,
            "baseline_value": None,
            "spike_score": round(spike_score, 4),
            "signal_source": "substack",
            "signal_category": "media",
            "fired": fired,
            "newsletter_count": count,
            "avg_subscribers": round(avg_subs, 0),
            "total_subscribers": total_subs,
            "sample_newsletters": topic_newsletter_names.get(topic, [])[:5],
        })

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(
        f"Substack: {len(all_newsletters)} newsletters, "
        f"{len(results)} topics, {fired_count} fired"
    )
    return results
