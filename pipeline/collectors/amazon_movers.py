"""
Amazon Movers & Shakers signal collector.
Scrapes Amazon Best Sellers "Movers and Shakers" pages using httpx + BeautifulSoup.
Tracks products with massive rank improvements — sudden rank jumps signal emerging demand.
Fires if rank_change > 500% improvement (e.g. rank 1000 -> rank 10 = 9900% improvement).
signal_category: behavior
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

AMAZON_BASE = "https://www.amazon.com"

# Movers & Shakers category pages
CATEGORIES = {
    "books": f"{AMAZON_BASE}/gp/movers-and-shakers/books/",
    "software": f"{AMAZON_BASE}/gp/movers-and-shakers/software/",
    "electronics": f"{AMAZON_BASE}/gp/movers-and-shakers/electronics/",
    "health-personal-care": f"{AMAZON_BASE}/gp/movers-and-shakers/health-personal-care/",
    "toys": f"{AMAZON_BASE}/gp/movers-and-shakers/toys-and-games/",
    "sports": f"{AMAZON_BASE}/gp/movers-and-shakers/sporting-goods/",
    "kitchen": f"{AMAZON_BASE}/gp/movers-and-shakers/kitchen/",
    "tools": f"{AMAZON_BASE}/gp/movers-and-shakers/tools/",
}

# Minimum rank improvement % to fire
RANK_CHANGE_FIRE_THRESHOLD = 500.0  # 500% improvement

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

STOPWORDS = {
    "the", "a", "an", "for", "and", "or", "with", "by", "in", "on",
    "at", "to", "of", "from", "set", "pack", "piece", "count",
    "inch", "ounce", "pound", "liter", "ml", "oz", "lb",
    "men", "women", "kids", "adult", "size", "color", "black",
    "white", "blue", "red", "green", "large", "small", "medium",
    "new", "original", "premium", "professional", "pro",
}


def _parse_rank_change(text: str) -> float:
    """
    Parse rank change text like '#1,234 (2,500% increase)' or '↑ 1,500%'.
    Returns the percentage improvement as a float (e.g. 2500.0 for 2500%).
    """
    # Look for patterns like "2,500%" or "2500%"
    match = re.search(r"([\d,]+)\s*%", text.replace(",", ""))
    if match:
        return float(match.group(1).replace(",", ""))

    # Look for "X times" language
    match_times = re.search(r"(\d+)\s*times", text.lower())
    if match_times:
        return (float(match_times.group(1)) - 1.0) * 100.0

    return 0.0


def _parse_rank_number(text: str) -> int:
    """Parse rank strings like '#1,234' to integer."""
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


@retry_with_backoff(max_retries=3)
def _scrape_movers_page(category: str, url: str) -> list[dict]:
    """
    Scrape an Amazon Movers & Shakers page.
    Returns list of product dicts with rank change info.
    """
    response = httpx.get(url, headers=HEADERS, timeout=30, follow_redirects=True)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    products = []

    # Amazon Movers & Shakers specific selectors
    # Products are typically in a zg-item-immersion or similar container
    items = (
        soup.select(".zg-item-immersion") or
        soup.select(".zg-grid-general-faceout") or
        soup.select("[class*='zg-item']") or
        soup.select("li.zg-item") or
        []
    )

    # Fallback: find any list items in the movers section
    if not items:
        items = soup.select(".a-section.zg-clearfix li") or soup.select("li")[:50]

    for item in items[:50]:
        try:
            # Product title
            title_el = (
                item.find(class_=re.compile(r"title|name|product", re.I)) or
                item.find("span", class_=re.compile(r"title", re.I)) or
                item.find("div", class_=re.compile(r"title", re.I)) or
                item.find("a", class_=re.compile(r"title", re.I))
            )
            # If no class-based match, try the first <a> with text
            if not title_el:
                links = item.find_all("a")
                for link in links:
                    txt = link.get_text(strip=True)
                    if len(txt) > 10:
                        title_el = link
                        break

            title = title_el.get_text(strip=True)[:200] if title_el else ""

            # Rank change — look for percentage strings
            rank_change_pct = 0.0
            all_text = item.get_text(" ", strip=True)

            # Pattern: "X,XXX%" or "X%"
            pct_matches = re.findall(r"([\d,]+)%", all_text)
            for pct_str in pct_matches:
                val = float(pct_str.replace(",", ""))
                if val > rank_change_pct:
                    rank_change_pct = val

            # Current rank
            rank_text_el = item.find(class_=re.compile(r"rank|number", re.I))
            rank_text = rank_text_el.get_text(strip=True) if rank_text_el else ""
            current_rank = _parse_rank_number(rank_text) if rank_text else 0

            # Product link
            link_el = item.find("a", href=re.compile(r"/dp/|/gp/product/"))
            product_url = ""
            if link_el:
                href = link_el.get("href", "")
                product_url = f"{AMAZON_BASE}{href}" if href.startswith("/") else href

            # Price
            price_el = item.find(class_=re.compile(r"price|Price", re.I))
            price_text = price_el.get_text(strip=True) if price_el else ""
            price = 0.0
            price_match = re.search(r"\$\s*([\d.]+)", price_text)
            if price_match:
                price = float(price_match.group(1))

            if title:
                products.append({
                    "title": title,
                    "rank_change_pct": rank_change_pct,
                    "current_rank": current_rank,
                    "category": category,
                    "url": product_url,
                    "price": price,
                })

        except Exception as e:
            logger.debug(f"Amazon: failed to parse item in {category}: {e}")
            continue

    return products


def _extract_topic_keywords(title: str) -> list[str]:
    """Extract topic keywords from a product title."""
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", title.lower())
    filtered = [w for w in words if w not in STOPWORDS and len(w) >= 3]

    topics = list(set(filtered))

    # Bigrams
    for i in range(len(filtered) - 1):
        bigram = f"{filtered[i]} {filtered[i+1]}"
        if len(bigram) >= 8:
            topics.append(bigram)

    return topics


def collect() -> list[dict]:
    """
    Scrapes Amazon Movers & Shakers pages for products with massive rank improvements.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, rank_change_pct,
                     product_title, category, price}.
    Fires if rank_change > 500%.
    signal_category: behavior
    """
    logger.info("Collecting Amazon Movers & Shakers signals...")
    results = []

    all_products = []

    for category, url in CATEGORIES.items():
        try:
            products = _scrape_movers_page(category, url)
            all_products.extend(products)
            logger.debug(f"Amazon [{category}]: {len(products)} products scraped")
            time.sleep(2)  # Respectful rate limiting
        except Exception as e:
            logger.warning(f"Amazon: failed to scrape {category}: {e}")
            time.sleep(3)

    if not all_products:
        logger.warning("Amazon: no products scraped from any category")
        return results

    logger.debug(f"Amazon: {len(all_products)} total products collected")

    # Find products that actually have rank change data
    products_with_data = [p for p in all_products if p["rank_change_pct"] > 0]
    max_change = max((p["rank_change_pct"] for p in products_with_data), default=1.0)

    # Products that fire based on rank change threshold
    fired_products = [p for p in all_products if p["rank_change_pct"] >= RANK_CHANGE_FIRE_THRESHOLD]

    for product in all_products:
        rank_change = product["rank_change_pct"]
        title = product["title"]
        category = product["category"]

        spike_score = rank_change / max_change if max_change > 0 else 0.0
        keywords = _extract_topic_keywords(title)

        results.append({
            "topic": title.lower()[:80],
            "raw_value": rank_change,
            "baseline_value": 0.0,  # 0 = no change baseline
            "spike_score": round(spike_score, 4),
            "signal_source": "amazon_movers",
            "signal_category": "behavior",
            "fired": rank_change >= RANK_CHANGE_FIRE_THRESHOLD,
            "rank_change_pct": rank_change,
            "current_rank": product["current_rank"],
            "product_title": title,
            "ks_category": category,
            "price": product["price"],
            "keywords": keywords[:6],
            "url": product["url"],
        })

    # Also aggregate by extracted keywords across all movers
    keyword_changes: dict[str, list[float]] = defaultdict(list)
    keyword_products: dict[str, list[str]] = defaultdict(list)

    for product in fired_products:
        keywords = _extract_topic_keywords(product["title"])
        for kw in keywords:
            keyword_changes[kw].append(product["rank_change_pct"])
            if len(keyword_products[kw]) < 3:
                keyword_products[kw].append(product["title"])

    # Topics appearing in 2+ movers
    multi_movers = {
        kw: changes for kw, changes in keyword_changes.items()
        if len(changes) >= 2
    }

    for kw, changes in sorted(multi_movers.items(), key=lambda x: len(x[1]), reverse=True)[:15]:
        avg_change = sum(changes) / len(changes)
        results.append({
            "topic": f"amazon_theme:{kw}",
            "raw_value": avg_change,
            "baseline_value": 0.0,
            "spike_score": round(min(avg_change / 2000.0, 1.0), 4),
            "signal_source": "amazon_movers",
            "signal_category": "behavior",
            "fired": avg_change >= RANK_CHANGE_FIRE_THRESHOLD,
            "rank_change_pct": round(avg_change, 1),
            "product_count": len(changes),
            "sample_products": keyword_products[kw],
        })

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(
        f"Amazon Movers: {len(all_products)} products, "
        f"{len(fired_products)} above threshold, {len(results)} signals, {fired_count} fired"
    )
    return results
