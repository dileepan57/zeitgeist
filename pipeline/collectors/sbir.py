"""
SBIR/STTR Government Grant signal collector.
Uses SBIR.gov API to fetch recent Small Business Innovation Research awards.
Groups by technology keywords in abstracts to find government-funded emerging areas.
Government money flowing into a tech = validated demand + long runway = strong builder signal.
signal_category: builder
"""
import re
import time
from collections import defaultdict, Counter
from datetime import date, timedelta
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

SBIR_AWARDS_API = "https://www.sbir.gov/api/awards.json"
SBIR_SOLICITATIONS_API = "https://www.sbir.gov/api/solicitations.json"

# Technology keyword groups to match against abstracts
TECH_KEYWORD_GROUPS = {
    "artificial intelligence": [
        "artificial intelligence", "machine learning", "deep learning",
        "neural network", "natural language processing", "computer vision",
        "large language model", "generative AI", "foundation model",
    ],
    "quantum technology": [
        "quantum computing", "quantum sensing", "quantum communication",
        "qubit", "quantum cryptography", "quantum network",
    ],
    "biotechnology": [
        "gene therapy", "CRISPR", "synthetic biology", "protein engineering",
        "mRNA", "cell therapy", "CAR-T", "bioinformatics", "genomics",
        "microbiome", "bioreactor",
    ],
    "autonomous systems": [
        "autonomous vehicle", "unmanned aerial", "drone", "robotics",
        "autonomous navigation", "swarm robotics", "human-robot",
    ],
    "cybersecurity": [
        "zero trust", "intrusion detection", "cyber defense", "malware",
        "cryptography", "post-quantum cryptography", "homomorphic encryption",
    ],
    "clean energy": [
        "solar energy", "wind energy", "battery storage", "fuel cell",
        "carbon capture", "energy storage", "hydrogen fuel", "grid storage",
        "EV charging", "perovskite",
    ],
    "advanced manufacturing": [
        "additive manufacturing", "3D printing", "digital twin",
        "smart manufacturing", "industry 4.0", "predictive maintenance",
    ],
    "space technology": [
        "satellite", "spacecraft", "launch vehicle", "lunar", "Mars",
        "orbital", "space debris", "in-space propulsion",
    ],
    "biomedical devices": [
        "wearable sensor", "implantable device", "biosensor", "point of care",
        "telemedicine", "remote monitoring", "diagnostic device",
    ],
    "edge computing": [
        "edge computing", "internet of things", "IoT", "embedded AI",
        "5G", "real-time processing", "fog computing",
    ],
}

# Minimum award count for a keyword to "fire"
MIN_AWARD_COUNT = 3


@retry_with_backoff(max_retries=3)
def _fetch_awards(page: int = 1, rows: int = 100, days: int = 30) -> dict:
    """
    Fetch recent SBIR/STTR awards from SBIR.gov API.
    Returns raw JSON response with awards list and metadata.
    """
    start_date = (date.today() - timedelta(days=days)).strftime("%m/%d/%Y")

    params = {
        "rows": rows,
        "start": (page - 1) * rows,
        "dateFrom": start_date,
        "dateTo": date.today().strftime("%m/%d/%Y"),
        "sortField": "award_date",
        "sortDir": "desc",
    }

    headers = {"User-Agent": "zeitgeist/1.0", "Accept": "application/json"}
    response = httpx.get(SBIR_AWARDS_API, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


@retry_with_backoff(max_retries=3)
def _fetch_solicitations(page: int = 1, rows: int = 50) -> dict:
    """
    Fetch open/recent SBIR/STTR solicitations.
    Solicitations = government is announcing they WANT to fund a topic area.
    """
    params = {
        "rows": rows,
        "start": (page - 1) * rows,
        "sortField": "solicitation_date",
        "sortDir": "desc",
    }

    headers = {"User-Agent": "zeitgeist/1.0", "Accept": "application/json"}
    response = httpx.get(SBIR_SOLICITATIONS_API, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def _match_keyword_groups(text: str) -> list[str]:
    """
    Match text against TECH_KEYWORD_GROUPS.
    Returns list of category names that match.
    """
    text_lower = text.lower()
    matched = []
    for category, keywords in TECH_KEYWORD_GROUPS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                matched.append(category)
                break
    return matched


def _extract_topic_words(text: str, top_n: int = 10) -> list[str]:
    """Extract the most frequent meaningful words from text."""
    STOPWORDS = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "for", "of", "and", "or", "but", "not",
        "with", "this", "that", "it", "in", "on", "at", "to", "by",
        "from", "as", "we", "our", "their", "which", "that", "these",
        "those", "also", "can", "may", "will", "use", "used", "using",
        "new", "novel", "proposed", "provide", "develop", "system",
        "method", "approach", "research", "project", "technology",
        "phase", "small", "business", "innovation", "company",
    }
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{3,}\b", text.lower())
    counts = Counter(w for w in words if w not in STOPWORDS)
    return [w for w, _ in counts.most_common(top_n)]


def collect() -> list[dict]:
    """
    Fetches SBIR/STTR awards and solicitations, groups by technology keywords.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, award_count,
                     total_award_value, agencies, sample_companies}.
    Fires if keyword appears in 3+ awards in the last 30 days.
    signal_category: builder
    """
    logger.info("Collecting SBIR/STTR government grant signals...")
    results = []

    # category -> list of award records
    category_awards: dict[str, list[dict]] = defaultdict(list)
    category_values: dict[str, float] = defaultdict(float)
    category_agencies: dict[str, set] = defaultdict(set)
    category_companies: dict[str, list] = defaultdict(list)

    # Fetch awards across multiple pages
    all_awards = []
    for page in range(1, 4):  # Up to 300 awards
        try:
            data = _fetch_awards(page=page, rows=100, days=30)

            # SBIR.gov returns data under different keys depending on version
            awards = (
                data.get("data", []) or
                data.get("results", []) or
                data.get("awards", []) or
                []
            )

            if not awards:
                break

            all_awards.extend(awards)
            logger.debug(f"SBIR: fetched page {page}, {len(awards)} awards")

            if len(awards) < 100:
                break  # No more pages

            time.sleep(2)

        except Exception as e:
            logger.warning(f"SBIR awards fetch failed (page {page}): {e}")
            break

    logger.debug(f"SBIR: {len(all_awards)} total awards fetched")

    for award in all_awards:
        abstract = award.get("abstract", "") or award.get("description", "") or ""
        title = award.get("award_title", "") or award.get("title", "") or ""
        agency = award.get("agency", "") or award.get("branch", "") or ""
        company = award.get("firm", "") or award.get("company", "") or ""
        amount = float(award.get("award_amount", 0) or 0)

        text = f"{title} {abstract}"

        matched_categories = _match_keyword_groups(text)

        for category in matched_categories:
            category_awards[category].append({
                "title": title[:100],
                "agency": agency,
                "company": company,
                "amount": amount,
            })
            category_values[category] += amount
            if agency:
                category_agencies[category].add(agency)
            if company and len(category_companies[category]) < 5:
                category_companies[category].append(company)

    if not category_awards:
        logger.warning("SBIR: No awards matched any keyword categories")
    else:
        max_count = max(len(v) for v in category_awards.values())

        for category, awards in category_awards.items():
            count = len(awards)
            total_value = category_values[category]
            agencies = list(category_agencies[category])
            companies = category_companies[category]

            spike_score = count / max_count if max_count > 0 else 0.0

            results.append({
                "topic": category,
                "raw_value": count,
                "baseline_value": None,  # No historical baseline without DB
                "spike_score": round(spike_score, 4),
                "signal_source": "sbir",
                "signal_category": "builder",
                "fired": count >= MIN_AWARD_COUNT,
                "award_count": count,
                "total_award_value_usd": round(total_value, 0),
                "agencies": agencies[:5],
                "sample_companies": companies[:5],
            })

    time.sleep(2)

    # --- SBIR Solicitations (forward-looking signal) ---
    try:
        sol_data = _fetch_solicitations(rows=50)
        solicitations = (
            sol_data.get("data", []) or
            sol_data.get("results", []) or
            sol_data.get("solicitations", []) or
            []
        )

        # Category -> solicitation count
        sol_categories: dict[str, list[str]] = defaultdict(list)

        for sol in solicitations:
            title = sol.get("solicitation_title", "") or sol.get("title", "") or ""
            description = sol.get("description", "") or ""
            agency = sol.get("agency", "") or ""

            text = f"{title} {description}"
            matched = _match_keyword_groups(text)
            for category in matched:
                sol_categories[category].append(f"{agency}: {title[:80]}")

        for category, sol_list in sol_categories.items():
            count = len(sol_list)
            results.append({
                "topic": f"solicitation:{category}",
                "raw_value": count,
                "baseline_value": None,
                "spike_score": round(min(count / 10.0, 1.0), 4),
                "signal_source": "sbir_solicitations",
                "signal_category": "builder",
                "fired": count >= 2,
                "solicitation_count": count,
                "sample_solicitations": sol_list[:3],
            })

        logger.debug(f"SBIR: {len(sol_categories)} solicitation category signals")

    except Exception as e:
        logger.warning(f"SBIR solicitations fetch failed: {e}")

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(f"SBIR: {len(results)} signals, {fired_count} fired (3+ awards)")
    return results
