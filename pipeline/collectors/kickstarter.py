"""
Kickstarter overfunding signal collector.
Scrapes Kickstarter discover page using httpx + BeautifulSoup.
Focuses on projects that have raised > 200% of goal (overfunding ratio).
Overfunding = unexpected demand = market gap being validated in real-time.
signal_category: money
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

KICKSTARTER_BASE = "https://www.kickstarter.com"

# Category discovery pages to scrape
KICKSTARTER_CATEGORIES = [
    ("Technology", "https://www.kickstarter.com/discover/categories/technology?sort=popularity"),
    ("Design", "https://www.kickstarter.com/discover/categories/design?sort=popularity"),
    ("Games", "https://www.kickstarter.com/discover/categories/games?sort=popularity"),
    ("Health", "https://www.kickstarter.com/discover/categories/health?sort=popularity"),
    ("Science", "https://www.kickstarter.com/discover/categories/science?sort=popularity"),
    ("Food", "https://www.kickstarter.com/discover/categories/food?sort=popularity"),
    ("Fashion", "https://www.kickstarter.com/discover/categories/fashion?sort=popularity"),
    ("Crafts", "https://www.kickstarter.com/discover/categories/crafts?sort=popularity"),
]

# Also check trending most-funded
KICKSTARTER_TRENDING = "https://www.kickstarter.com/discover/advanced?sort=most_funded&page=1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OVERFUNDING_THRESHOLD = 2.0  # 200% of goal

STOPWORDS = {
    "the", "a", "an", "for", "and", "or", "with", "your",
    "our", "new", "best", "first", "world", "most", "ever",
    "unique", "ultimate", "perfect", "all", "any", "every",
    "one", "two", "three", "get", "make", "built", "designed",
}


def _parse_currency(text: str) -> float:
    """Parse currency strings like '$1,234' or '£500' to float."""
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _extract_percent(text: str) -> float:
    """Extract percentage value from strings like '342% funded'."""
    match = re.search(r"(\d[\d,]*)\s*%", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return 0.0


@retry_with_backoff(max_retries=3)
def _scrape_category_page(url: str) -> list[dict]:
    """
    Scrape a Kickstarter category page and extract project data.
    Returns list of project dicts with funding info.
    """
    response = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    projects = []

    # Kickstarter uses data attributes on project cards
    # Multiple possible selectors depending on page version
    project_cards = (
        soup.select("[data-testid='project-card']") or
        soup.select(".js-project-card") or
        soup.select("li.projects-grid_cell") or
        soup.select("div[class*='project']") or
        []
    )

    # Fallback: find all <article> tags (KS often uses these)
    if not project_cards:
        project_cards = soup.find_all("article", limit=30)

    for card in project_cards[:30]:
        try:
            # Try to extract project name
            name_el = (
                card.find("h3") or
                card.find("h2") or
                card.find(attrs={"data-testid": "project-name"}) or
                card.find(class_=re.compile(r"title|name", re.I))
            )
            name = name_el.get_text(strip=True) if name_el else ""

            # Funding percentage
            pct_el = (
                card.find(string=re.compile(r"\d+%")) or
                card.find(attrs={"data-percent-raised": True}) or
                card.find(class_=re.compile(r"percent|funded", re.I))
            )

            pct_funded = 0.0
            if pct_el:
                if hasattr(pct_el, "get") and pct_el.get("data-percent-raised"):
                    pct_funded = float(pct_el["data-percent-raised"])
                else:
                    pct_text = pct_el if isinstance(pct_el, str) else pct_el.get_text()
                    pct_funded = _extract_percent(pct_text)

            # Amount raised
            raised_el = card.find(attrs={"data-pledged": True})
            amount_raised = float(raised_el["data-pledged"]) if raised_el else 0.0

            # Goal amount
            goal_el = card.find(attrs={"data-goal": True})
            goal = float(goal_el["data-goal"]) if goal_el else 0.0

            # Compute overfunding ratio from raw data if available
            if goal > 0 and amount_raised > 0:
                overfunding_ratio = amount_raised / goal
            elif pct_funded > 0:
                overfunding_ratio = pct_funded / 100.0
            else:
                overfunding_ratio = 0.0

            # Category / tags
            category_el = card.find(attrs={"data-category": True})
            category = category_el["data-category"] if category_el else ""

            # Short description / tagline
            desc_el = (
                card.find("p", class_=re.compile(r"desc|sub|blurb", re.I)) or
                card.find("p")
            )
            desc = desc_el.get_text(strip=True)[:200] if desc_el else ""

            # Link
            link_el = card.find("a", href=re.compile(r"/projects/"))
            url_path = link_el["href"] if link_el else ""
            full_url = f"{KICKSTARTER_BASE}{url_path}" if url_path.startswith("/") else url_path

            if name:  # Only include if we got a name
                projects.append({
                    "name": name,
                    "description": desc,
                    "overfunding_ratio": round(overfunding_ratio, 3),
                    "amount_raised": amount_raised,
                    "goal": goal,
                    "category": category,
                    "url": full_url,
                })

        except Exception as e:
            logger.debug(f"Kickstarter: failed to parse card: {e}")
            continue

    return projects


def _extract_keywords(name: str, description: str) -> list[str]:
    """Extract topic keywords from project name and description."""
    text = f"{name} {description}"
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", text.lower())
    filtered = [w for w in words if w not in STOPWORDS and len(w) >= 3]

    topics = []
    for w in set(filtered):
        topics.append(w)

    # Bigrams from name (high signal for new product categories)
    name_words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", name.lower())
    name_filtered = [w for w in name_words if w not in STOPWORDS]
    for i in range(len(name_filtered) - 1):
        topics.append(f"{name_filtered[i]} {name_filtered[i+1]}")

    return topics


def collect() -> list[dict]:
    """
    Scrapes Kickstarter category pages for overfunded projects.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, overfunding_ratio,
                     amount_raised, goal, project_name, category}.
    Fires only if overfunding_ratio > 2.0 (200%+ funded).
    signal_category: money
    """
    logger.info("Collecting Kickstarter overfunding signals...")
    results = []

    all_projects = []

    # Scrape category pages
    for category_name, url in KICKSTARTER_CATEGORIES:
        try:
            projects = _scrape_category_page(url)
            for p in projects:
                p["source_category"] = category_name
            all_projects.extend(projects)
            logger.debug(f"Kickstarter: {len(projects)} projects from {category_name}")
            time.sleep(2)  # Respectful rate limiting
        except Exception as e:
            logger.warning(f"Kickstarter: failed to scrape {category_name}: {e}")

    # Scrape trending most-funded
    try:
        trending_projects = _scrape_category_page(KICKSTARTER_TRENDING)
        for p in trending_projects:
            p["source_category"] = "Trending"
        all_projects.extend(trending_projects)
        logger.debug(f"Kickstarter: {len(trending_projects)} trending projects")
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Kickstarter: failed to scrape trending: {e}")

    if not all_projects:
        logger.warning("Kickstarter: no projects scraped")
        return results

    logger.debug(f"Kickstarter: {len(all_projects)} total projects collected")

    # Filter to overfunded projects and add as individual signals
    overfunded = [p for p in all_projects if p["overfunding_ratio"] >= OVERFUNDING_THRESHOLD]
    max_ratio = max((p["overfunding_ratio"] for p in overfunded), default=1.0)

    for project in overfunded:
        ratio = project["overfunding_ratio"]
        name = project["name"]
        description = project["description"]

        keywords = _extract_keywords(name, description)
        spike_score = ratio / max_ratio if max_ratio > 0 else 0.0

        results.append({
            "topic": name.lower()[:60],
            "raw_value": round(ratio, 3),
            "baseline_value": 1.0,  # 1.0 = exactly at funding goal
            "spike_score": round(spike_score, 4),
            "signal_source": "kickstarter",
            "signal_category": "money",
            "fired": True,  # All results here already pass the threshold
            "overfunding_ratio": round(ratio, 3),
            "amount_raised": project["amount_raised"],
            "goal": project["goal"],
            "project_name": name,
            "ks_category": project.get("source_category", ""),
            "keywords": keywords[:8],
            "url": project["url"],
        })

    # Also aggregate by keyword to find topic-level signals
    keyword_ratios: dict[str, list[float]] = defaultdict(list)
    keyword_projects: dict[str, list[str]] = defaultdict(list)

    for project in overfunded:
        keywords = _extract_keywords(project["name"], project["description"])
        for kw in keywords:
            keyword_ratios[kw].append(project["overfunding_ratio"])
            if len(keyword_projects[kw]) < 3:
                keyword_projects[kw].append(project["name"])

    # Topics appearing in multiple overfunded projects
    multi_project_keywords = {
        kw: ratios for kw, ratios in keyword_ratios.items()
        if len(ratios) >= 2
    }

    for kw, ratios in sorted(multi_project_keywords.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
        avg_ratio = sum(ratios) / len(ratios)
        results.append({
            "topic": f"ks_theme:{kw}",
            "raw_value": round(avg_ratio, 3),
            "baseline_value": 1.0,
            "spike_score": round(min(avg_ratio / 5.0, 1.0), 4),
            "signal_source": "kickstarter",
            "signal_category": "money",
            "fired": avg_ratio >= OVERFUNDING_THRESHOLD,
            "overfunding_ratio": round(avg_ratio, 3),
            "project_count": len(ratios),
            "sample_projects": keyword_projects[kw],
        })

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(
        f"Kickstarter: {len(all_projects)} projects scraped, "
        f"{len(overfunded)} overfunded, {len(results)} signals, {fired_count} fired"
    )
    return results
