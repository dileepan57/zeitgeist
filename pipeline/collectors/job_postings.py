"""
Job postings signal collector.
Uses Adzuna API (ADZUNA_APP_ID, ADZUNA_APP_KEY env vars) to track
job posting counts by technology keyword category.
Computes spike vs 30-day rolling average to detect hiring surges.
Hiring surges = companies are betting money on a technology = strong behavior signal.
signal_category: behavior
"""
import os
import time
from datetime import date, timedelta
from collections import defaultdict
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

ADZUNA_API_BASE = "https://api.adzuna.com/v1/api/jobs"

# Countries to query — each gives independent demand signal
COUNTRIES = ["us", "gb", "ca", "au"]

# Technology categories to track
TECH_CATEGORIES = [
    "AI",
    "machine learning",
    "climate tech",
    "biotech",
    "web3",
    "AR/VR",
    "quantum computing",
    "cybersecurity",
    "robotics",
    "autonomous vehicles",
    "synthetic biology",
    "edge computing",
    "spatial computing",
    "no-code",
    "developer tools",
]

# Search query overrides where needed (Adzuna free text search)
CATEGORY_QUERIES = {
    "AI": "artificial intelligence OR generative AI OR large language model",
    "machine learning": "machine learning OR deep learning OR MLOps",
    "climate tech": "climate tech OR cleantech OR renewable energy OR carbon capture",
    "biotech": "biotech OR bioinformatics OR gene therapy OR CRISPR",
    "web3": "web3 OR blockchain OR smart contracts OR DeFi OR NFT",
    "AR/VR": "augmented reality OR virtual reality OR mixed reality OR XR OR metaverse",
    "quantum computing": "quantum computing OR quantum engineer OR quantum software",
    "cybersecurity": "cybersecurity OR information security OR zero trust OR SIEM",
    "robotics": "robotics OR robot engineer OR ROS OR autonomous systems",
    "autonomous vehicles": "autonomous vehicles OR self-driving OR AV software OR ADAS",
    "synthetic biology": "synthetic biology OR protein engineering OR biofoundry",
    "edge computing": "edge computing OR edge AI OR IoT OR embedded AI",
    "spatial computing": "spatial computing OR Apple Vision OR holographic OR 3D UI",
    "no-code": "no-code OR low-code OR citizen developer OR visual programming",
    "developer tools": "developer tools OR DevEx OR platform engineering OR internal developer",
}


@retry_with_backoff(max_retries=3)
def _fetch_job_count(
    app_id: str,
    app_key: str,
    country: str,
    what: str,
    max_days_old: int = 7,
) -> int:
    """
    Fetch total job count for a keyword query in a country.
    Returns the total count from Adzuna's count field.
    """
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": what,
        "max_days_old": max_days_old,
        "results_per_page": 1,  # We only need the count
        "content-type": "application/json",
    }

    url = f"{ADZUNA_API_BASE}/{country}/search/1"
    response = httpx.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    return data.get("count", 0)


@retry_with_backoff(max_retries=3)
def _fetch_job_count_30d(
    app_id: str,
    app_key: str,
    country: str,
    what: str,
) -> int:
    """
    Fetch job count for last 30 days to use as rolling baseline.
    """
    return _fetch_job_count(app_id, app_key, country, what, max_days_old=30)


@retry_with_backoff(max_retries=3)
def _fetch_top_companies(
    app_id: str,
    app_key: str,
    country: str,
    what: str,
) -> list[str]:
    """
    Fetch top hiring companies for a keyword in a country.
    Returns list of company names from first page of results.
    """
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": what,
        "max_days_old": 7,
        "results_per_page": 10,
        "content-type": "application/json",
        "sort_by": "relevance",
    }
    url = f"{ADZUNA_API_BASE}/{country}/search/1"
    response = httpx.get(url, params=params, timeout=30)
    response.raise_for_status()
    jobs = response.json().get("results", [])
    companies = []
    seen = set()
    for job in jobs:
        company = job.get("company", {}).get("display_name", "")
        if company and company not in seen:
            companies.append(company)
            seen.add(company)
    return companies[:5]


def collect() -> list[dict]:
    """
    Fetches Adzuna job posting counts across tech categories and countries.
    Computes 7-day count vs 30-day baseline to detect hiring surges.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, job_count_7d,
                     job_count_30d_avg, countries_tracked, top_companies}.
    signal_category: behavior
    """
    logger.info("Collecting Adzuna job posting signals...")
    results = []

    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        logger.error("Adzuna: ADZUNA_APP_ID or ADZUNA_APP_KEY not set — skipping")
        return results

    for category in TECH_CATEGORIES:
        query = CATEGORY_QUERIES.get(category, category)

        category_7d_counts = []
        category_30d_counts = []
        all_companies = []

        for country in COUNTRIES:
            try:
                count_7d = _fetch_job_count(app_id, app_key, country, query, max_days_old=7)
                time.sleep(1)
                count_30d = _fetch_job_count_30d(app_id, app_key, country, query)
                time.sleep(1)

                category_7d_counts.append(count_7d)
                # 30d count -> per-7d equivalent
                baseline_7d = count_30d / (30 / 7)
                category_30d_counts.append(baseline_7d)

                logger.debug(
                    f"Adzuna [{country}] '{category}': "
                    f"7d={count_7d}, 30d_equiv={baseline_7d:.0f}"
                )

                # Fetch top companies for US only (reduces API calls)
                if country == "us" and count_7d > 0:
                    try:
                        companies = _fetch_top_companies(app_id, app_key, country, query)
                        all_companies.extend(companies)
                        time.sleep(1)
                    except Exception as e:
                        logger.debug(f"Adzuna: company fetch failed for {category}: {e}")

            except Exception as e:
                logger.warning(f"Adzuna [{country}] '{category}': {e}")

            time.sleep(1.5)  # Polite pacing between countries

        if not category_7d_counts:
            continue

        total_7d = sum(category_7d_counts)
        total_baseline = sum(category_30d_counts)

        if total_baseline > 0:
            spike_score = (total_7d - total_baseline) / total_baseline
        else:
            spike_score = 0.0

        # Normalize to 0-1 range for spike_score (cap at 200% spike = 1.0)
        normalized_spike = min(max(spike_score + 1.0, 0) / 3.0, 1.0)

        results.append({
            "topic": category,
            "raw_value": total_7d,
            "baseline_value": round(total_baseline, 1),
            "spike_score": round(normalized_spike, 4),
            "signal_source": "adzuna",
            "signal_category": "behavior",
            "fired": spike_score > 0.20,  # 20% above 7-day baseline
            "job_count_7d": total_7d,
            "job_count_30d_avg": round(total_baseline, 1),
            "raw_spike_ratio": round(spike_score, 4),
            "countries_tracked": COUNTRIES,
            "top_companies": list(set(all_companies))[:5],
        })

        logger.debug(
            f"Adzuna '{category}': {total_7d} jobs (7d), "
            f"baseline={total_baseline:.0f}, spike={spike_score:.2%}"
        )

        time.sleep(2)  # Adzuna rate limit: courtesy sleep between categories

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(f"Adzuna: {len(results)} categories, {fired_count} fired (>20% spike)")
    return results
