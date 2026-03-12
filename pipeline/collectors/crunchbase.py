"""
Crunchbase funding signal collector.
Uses Crunchbase Basic API if CRUNCHBASE_API_KEY is available,
otherwise scrapes public funding data from TechCrunch and Crunchbase News.
Tracks recent funding rounds by category — money flowing into a space = conviction signal.
Graceful fallback if no API key: uses public news sources.
signal_category: money
"""
import os
import re
import time
from collections import defaultdict
from datetime import date, timedelta
from loguru import logger
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

CRUNCHBASE_API_BASE = "https://api.crunchbase.com/api/v4"

# Fallback: TechCrunch funding news (public)
TECHCRUNCH_FUNDING_URL = "https://techcrunch.com/tag/funding/"

# Fallback: Crunchbase public news page
CB_NEWS_URL = "https://news.crunchbase.com/funding/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Technology category keywords to classify funding rounds
FUNDING_CATEGORIES = {
    "AI & Machine Learning": [
        "artificial intelligence", "machine learning", "AI", "LLM",
        "generative AI", "computer vision", "NLP", "foundation model",
    ],
    "Biotech & Genomics": [
        "biotech", "genomics", "gene therapy", "CRISPR", "synthetic biology",
        "protein", "cell therapy", "drug discovery", "biopharma",
    ],
    "Climate Tech": [
        "climate", "cleantech", "renewable", "solar", "wind", "EV",
        "battery", "carbon", "green energy", "sustainability",
    ],
    "Fintech": [
        "fintech", "payments", "banking", "lending", "insurance",
        "blockchain", "crypto", "DeFi", "regtech", "wealthtech",
    ],
    "Cybersecurity": [
        "cybersecurity", "security", "zero trust", "identity",
        "threat detection", "compliance", "privacy",
    ],
    "Healthcare": [
        "healthtech", "digital health", "telehealth", "medtech",
        "diagnostics", "wearable", "mental health", "hospital",
    ],
    "Space Technology": [
        "space", "satellite", "launch", "orbital", "aerospace",
    ],
    "Robotics & Automation": [
        "robotics", "autonomous", "automation", "drone", "warehouse",
    ],
    "Developer Tools": [
        "developer tools", "DevOps", "platform engineering", "API",
        "developer productivity", "cloud infrastructure",
    ],
    "Edtech": [
        "edtech", "education", "learning", "training", "upskilling",
        "e-learning", "tutoring",
    ],
    "Web3 & Blockchain": [
        "web3", "blockchain", "NFT", "DeFi", "DAO", "metaverse",
        "digital assets", "tokenization",
    ],
    "Quantum Computing": [
        "quantum computing", "qubit", "quantum hardware",
        "quantum software", "quantum networking",
    ],
    "No-Code / Low-Code": [
        "no-code", "low-code", "citizen developer", "visual programming",
        "workflow automation",
    ],
    "Creator Economy": [
        "creator economy", "creator tools", "content creator",
        "influencer", "newsletter", "community platform",
    ],
}

# Old-style CB slugs for API queries
CB_CATEGORY_SLUGS = [
    "artificial-intelligence", "machine-learning", "climate-tech",
    "health-care", "fintech", "edtech", "biotech", "cybersecurity",
    "developer-tools", "no-code", "robotics", "quantum-computing",
    "augmented-reality", "creator-economy", "mental-health",
]


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


@retry_with_backoff(max_retries=3)
def _fetch_crunchbase_api(api_key: str, category_slug: str, days: int = 30) -> list[dict]:
    """
    Fetch recent funding rounds from Crunchbase Basic API for a category slug.
    Returns list of funding round entity dicts.
    """
    headers = {
        "X-cb-user-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "zeitgeist/1.0",
    }

    # Use the v4 searches endpoint
    url = f"{CRUNCHBASE_API_BASE}/searches/funding_rounds"
    payload = {
        "field_ids": [
            "announced_on",
            "funded_organization_description",
            "funded_organization_categories",
            "funded_organization_name",
            "investment_type",
            "money_raised",
        ],
        "predicate": {
            "field_id": "announced_on",
            "operator_id": "gte",
            "values": [_days_ago(days)],
        },
        "order": [{"field_id": "money_raised", "sort": "desc"}],
        "limit": 25,
    }

    response = httpx.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json().get("entities", [])


@retry_with_backoff(max_retries=3)
def _scrape_techcrunch_funding() -> list[dict]:
    """
    Scrape TechCrunch funding news as a fallback.
    Returns list of funding article dicts.
    """
    response = httpx.get(TECHCRUNCH_FUNDING_URL, headers=HEADERS, timeout=30, follow_redirects=True)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = []

    items = (
        soup.select("article") or
        soup.select(".post-block") or
        soup.select("[class*='article']") or
        []
    )

    for item in items[:30]:
        try:
            title_el = item.find("h2") or item.find("h3") or item.find("a")
            title = title_el.get_text(strip=True) if title_el else ""

            desc_el = item.find("p") or item.find(class_=re.compile(r"desc|excerpt|summary", re.I))
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""

            # Extract funding amount from text
            amount_match = re.search(
                r"\$\s*([\d.]+)\s*(M|B|K|million|billion|thousand)",
                f"{title} {description}",
                re.I,
            )
            amount = 0.0
            if amount_match:
                num = float(amount_match.group(1))
                unit = amount_match.group(2).upper()
                multipliers = {"M": 1e6, "MILLION": 1e6, "B": 1e9, "BILLION": 1e9, "K": 1e3, "THOUSAND": 1e3}
                amount = num * multipliers.get(unit, 1)

            if title:
                articles.append({
                    "title": title,
                    "description": description,
                    "amount": amount,
                    "source": "techcrunch",
                })
        except Exception as e:
            logger.debug(f"TechCrunch: parse error: {e}")

    return articles


@retry_with_backoff(max_retries=3)
def _scrape_crunchbase_news() -> list[dict]:
    """Scrape Crunchbase News public funding page."""
    response = httpx.get(CB_NEWS_URL, headers=HEADERS, timeout=30, follow_redirects=True)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = []

    items = soup.select("article") or soup.select(".article-card") or []

    for item in items[:30]:
        try:
            title_el = item.find("h2") or item.find("h3") or item.find("a")
            title = title_el.get_text(strip=True) if title_el else ""

            desc_el = item.find("p")
            description = desc_el.get_text(strip=True)[:300] if desc_el else ""

            amount_match = re.search(
                r"\$\s*([\d.]+)\s*(M|B|K|million|billion)",
                f"{title} {description}",
                re.I,
            )
            amount = 0.0
            if amount_match:
                num = float(amount_match.group(1))
                unit = amount_match.group(2).upper()
                multipliers = {"M": 1e6, "MILLION": 1e6, "B": 1e9, "BILLION": 1e9, "K": 1e3}
                amount = num * multipliers.get(unit, 1)

            if title:
                articles.append({
                    "title": title,
                    "description": description,
                    "amount": amount,
                    "source": "crunchbase_news",
                })
        except Exception as e:
            logger.debug(f"Crunchbase News: parse error: {e}")

    return articles


def _classify_funding(title: str, description: str) -> list[str]:
    """Classify a funding round / article into tech categories."""
    text = f"{title} {description}".lower()
    matched = []
    for category, keywords in FUNDING_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in text:
                matched.append(category)
                break
    return matched


def _collect_with_api(api_key: str) -> tuple[dict, dict, str]:
    """Collect using Crunchbase API. Returns (category_rounds, category_amounts, source)."""
    category_rounds: dict[str, list[dict]] = defaultdict(list)
    category_amounts: dict[str, float] = defaultdict(float)

    # Fetch across all categories (one broad search, then classify)
    try:
        rounds = _fetch_crunchbase_api(api_key, "", days=30)
        for round_data in rounds:
            props = round_data.get("properties", {})
            company_name = props.get("funded_organization_name", "")
            description = props.get("funded_organization_description", "") or ""
            amount_raw = props.get("money_raised", {})
            if isinstance(amount_raw, dict):
                amount_usd = float(amount_raw.get("value_usd", 0) or 0)
            else:
                amount_usd = float(amount_raw or 0)

            categories_raw = props.get("funded_organization_categories", []) or []
            cb_categories = [c.get("value", "") for c in categories_raw if isinstance(c, dict)]

            matched = _classify_funding(company_name, description)
            matched.extend(cb_categories)
            matched = list(set(matched)) or ["Other"]

            for cat in matched:
                if cat == "Other":
                    continue
                category_rounds[cat].append({"company": company_name, "amount": amount_usd})
                category_amounts[cat] += amount_usd

        return category_rounds, category_amounts, "crunchbase_api"

    except Exception as e:
        logger.warning(f"Crunchbase API failed: {e}")
        return defaultdict(list), defaultdict(float), "failed"


def _collect_fallback() -> tuple[dict, dict, str]:
    """Fallback: scrape TechCrunch + Crunchbase News."""
    category_rounds: dict[str, list[dict]] = defaultdict(list)
    category_amounts: dict[str, float] = defaultdict(float)

    all_articles = []

    try:
        tc_articles = _scrape_techcrunch_funding()
        all_articles.extend(tc_articles)
        logger.debug(f"TechCrunch funding: {len(tc_articles)} articles")
        time.sleep(2)
    except Exception as e:
        logger.warning(f"TechCrunch scrape failed: {e}")

    try:
        cb_articles = _scrape_crunchbase_news()
        all_articles.extend(cb_articles)
        logger.debug(f"Crunchbase News: {len(cb_articles)} articles")
        time.sleep(2)
    except Exception as e:
        logger.warning(f"Crunchbase News scrape failed: {e}")

    for article in all_articles:
        matched = _classify_funding(article["title"], article["description"])
        if not matched:
            continue
        for cat in matched:
            category_rounds[cat].append({
                "company": article["title"][:80],
                "amount": article["amount"],
            })
            category_amounts[cat] += article["amount"]

    return category_rounds, category_amounts, "news_scrape"


def collect() -> list[dict]:
    """
    Fetches funding round data from Crunchbase API (if key available)
    or falls back to scraping TechCrunch/Crunchbase News.
    Groups by technology category.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, round_count,
                     total_funding_usd, avg_round_size_usd, data_source}.
    signal_category: money
    """
    logger.info("Collecting Crunchbase funding signals...")
    results = []

    api_key = os.environ.get("CRUNCHBASE_API_KEY")

    if api_key:
        category_rounds, category_amounts, data_source = _collect_with_api(api_key)
        if not category_rounds:
            # API failed, use fallback
            category_rounds, category_amounts, data_source = _collect_fallback()
    else:
        logger.info("Crunchbase: no API key — using public data fallback")
        category_rounds, category_amounts, data_source = _collect_fallback()

    if not category_rounds:
        logger.warning("Crunchbase: no funding data collected from any source")
        return results

    max_count = max(len(v) for v in category_rounds.values()) if category_rounds else 1
    max_amount = max(category_amounts.values()) if category_amounts else 1.0

    for category in list(FUNDING_CATEGORIES.keys()):
        if category not in category_rounds:
            continue

        rounds = category_rounds[category]
        count = len(rounds)
        total_amount = category_amounts[category]
        avg_round = total_amount / count if count > 0 else 0

        count_score = count / max_count if max_count > 0 else 0.0
        amount_score = total_amount / max_amount if max_amount > 0 else 0.0
        spike_score = (count_score * 0.6) + (amount_score * 0.4)

        results.append({
            "topic": category,
            "raw_value": count,
            "baseline_value": None,
            "spike_score": round(spike_score, 4),
            "signal_source": data_source,
            "signal_category": "money",
            "fired": count >= 3 or total_amount >= 50_000_000,
            "round_count": count,
            "total_funding_usd": round(total_amount, 0),
            "avg_round_size_usd": round(avg_round, 0),
            "data_source": data_source,
            "sample_companies": [r["company"] for r in rounds[:3]],
        })

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(
        f"Crunchbase: {sum(len(v) for v in category_rounds.values())} rounds, "
        f"{len(results)} categories, {fired_count} fired (via {data_source})"
    )
    return results
