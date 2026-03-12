"""
Discord server growth signal collector.
Scrapes Disboard (https://disboard.org/servers) for rapidly growing servers.
Groups by server tags/categories to identify community formation around topics.
Community formation = early adopters organizing = strong early signal.
Fires if topic appears in 5+ growing servers.
signal_category: community
"""
import re
import time
from collections import defaultdict, Counter
from loguru import logger
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

DISBOARD_BASE = "https://disboard.org"

# Sort options: "bump" = recently bumped (active/growing), "member_count" = largest
DISBOARD_SORT_OPTIONS = [
    ("bump", "Recently Active"),
    ("member_count", "Largest"),
]

# Category pages to probe for emerging communities
DISBOARD_CATEGORIES = [
    "technology",
    "science",
    "ai",
    "cryptocurrency",
    "programming",
    "gaming",
    "health",
    "education",
    "creative",
    "business",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://disboard.org/",
}

STOPWORDS = {
    "the", "a", "an", "for", "and", "or", "with", "your", "our",
    "you", "that", "this", "it", "to", "of", "in", "on", "at",
    "by", "from", "not", "no", "yes", "be", "been", "server",
    "discord", "community", "chat", "talk", "discuss", "general",
    "welcome", "join", "official", "fan", "club", "group", "fun",
    "social", "friendly", "chill", "vibe", "hub", "world",
}

MIN_FIRE_COUNT = 5  # Minimum servers sharing a topic tag to fire


@retry_with_backoff(max_retries=3)
def _scrape_disboard_page(url: str) -> list[dict]:
    """
    Scrape a Disboard listing page and extract server data.
    Returns list of server dicts with name, member count, tags.
    """
    response = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    servers = []

    # Disboard server cards
    server_cards = (
        soup.select(".server-card") or
        soup.select("[class*='server-card']") or
        soup.select(".server") or
        soup.select("li[class*='server']") or
        []
    )

    # Fallback: find all divs with data-server-id
    if not server_cards:
        server_cards = soup.find_all(attrs={"data-server-id": True})

    # Last fallback: look for sections with member count patterns
    if not server_cards:
        server_cards = soup.find_all("article")

    for card in server_cards[:30]:
        try:
            # Server name
            name_el = (
                card.find(class_=re.compile(r"server-name|title|name", re.I)) or
                card.find("h3") or
                card.find("h2") or
                card.find("strong")
            )
            name = name_el.get_text(strip=True) if name_el else ""

            # Member count
            member_text = ""
            member_count = 0
            member_el = card.find(string=re.compile(r"\d[\d,]*\s*(members?|online)", re.I))
            if member_el:
                member_text = member_el
                digits = re.sub(r"[^\d]", "", member_text.split()[0])
                member_count = int(digits) if digits else 0
            else:
                # Check data attribute
                mc_el = card.find(attrs={"data-member-count": True})
                if mc_el:
                    try:
                        member_count = int(mc_el["data-member-count"])
                    except (ValueError, KeyError):
                        pass

            # Tags
            tag_els = (
                card.select(".server-tag") or
                card.select("[class*='tag']") or
                card.select("span[class*='category']") or
                []
            )
            tags = [t.get_text(strip=True).lower() for t in tag_els if t.get_text(strip=True)]

            # Description / short description
            desc_el = (
                card.find(class_=re.compile(r"description|desc|summary", re.I)) or
                card.find("p")
            )
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""

            if name:
                servers.append({
                    "name": name,
                    "member_count": member_count,
                    "tags": tags,
                    "description": description,
                })

        except Exception as e:
            logger.debug(f"Disboard: failed to parse server card: {e}")
            continue

    return servers


@retry_with_backoff(max_retries=3)
def _scrape_disboard_category(category: str, sort: str = "bump") -> list[dict]:
    """
    Scrape Disboard category page filtered by sort.
    """
    url = f"{DISBOARD_BASE}/servers/tag/{category}?sort={sort}"
    return _scrape_disboard_page(url)


def _extract_topics_from_server(name: str, tags: list[str], description: str) -> list[str]:
    """
    Extract topic keywords from server name, tags, and description.
    Tags from Disboard are already curated — give them highest weight.
    """
    topics = []

    # Tags first (highest signal)
    for tag in tags:
        clean_tag = tag.strip().lower()
        if clean_tag and clean_tag not in STOPWORDS and len(clean_tag) >= 3:
            topics.append(clean_tag)

    # Name words
    name_words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", name.lower())
    filtered_name = [w for w in name_words if w not in STOPWORDS]
    topics.extend(filtered_name)

    # Bigrams from name
    for i in range(len(filtered_name) - 1):
        topics.append(f"{filtered_name[i]} {filtered_name[i+1]}")

    return list(set(topics))


def collect() -> list[dict]:
    """
    Scrapes Disboard for growing Discord servers, groups by topics.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, server_count,
                     avg_member_count, sample_servers}.
    Fires if topic appears in 5+ growing servers.
    signal_category: community
    """
    logger.info("Collecting Discord/Disboard community signals...")
    results = []

    all_servers = []

    # Scrape by category
    for category in DISBOARD_CATEGORIES:
        for sort, sort_label in DISBOARD_SORT_OPTIONS[:1]:  # Just "bump" (active servers)
            try:
                servers = _scrape_disboard_category(category, sort=sort)
                all_servers.extend(servers)
                logger.debug(
                    f"Disboard [{category}/{sort_label}]: {len(servers)} servers"
                )
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Disboard: failed for {category}/{sort}: {e}")
                time.sleep(3)

    # Also scrape the general "new" / recently active page
    try:
        general_servers = _scrape_disboard_page(f"{DISBOARD_BASE}/servers?sort=bump")
        all_servers.extend(general_servers)
        logger.debug(f"Disboard general: {len(general_servers)} servers")
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Disboard: failed to scrape general page: {e}")

    if not all_servers:
        logger.warning("Disboard: no servers scraped")
        return results

    logger.debug(f"Disboard: {len(all_servers)} total servers collected")

    # Aggregate by topic across all servers
    topic_server_count: dict[str, int] = defaultdict(int)
    topic_member_counts: dict[str, list[int]] = defaultdict(list)
    topic_server_names: dict[str, list[str]] = defaultdict(list)

    for server in all_servers:
        topics = _extract_topics_from_server(
            server["name"],
            server["tags"],
            server["description"],
        )
        member_count = server["member_count"]

        for topic in topics:
            topic_server_count[topic] += 1
            if member_count > 0:
                topic_member_counts[topic].append(member_count)
            if len(topic_server_names[topic]) < 5:
                topic_server_names[topic].append(server["name"])

    if not topic_server_count:
        logger.warning("Disboard: no topics extracted from servers")
        return results

    max_server_count = max(topic_server_count.values())

    for topic, server_count in sorted(
        topic_server_count.items(), key=lambda x: x[1], reverse=True
    )[:80]:
        member_list = topic_member_counts.get(topic, [])
        avg_members = sum(member_list) / len(member_list) if member_list else 0

        spike_score = server_count / max_server_count if max_server_count > 0 else 0.0

        results.append({
            "topic": topic,
            "raw_value": server_count,
            "baseline_value": MIN_FIRE_COUNT,  # Fire threshold as baseline
            "spike_score": round(spike_score, 4),
            "signal_source": "disboard",
            "signal_category": "community",
            "fired": server_count >= MIN_FIRE_COUNT,
            "server_count": server_count,
            "avg_member_count": round(avg_members, 0),
            "sample_servers": topic_server_names.get(topic, [])[:5],
        })

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(
        f"Disboard: {len(all_servers)} servers, {len(results)} topics, "
        f"{fired_count} fired (5+ servers)"
    )
    return results
