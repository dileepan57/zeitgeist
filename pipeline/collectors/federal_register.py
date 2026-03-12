"""
Federal Register regulatory signal collector.
Uses Federal Register API (free, no auth) to fetch proposed rules and notices
from the last 14 days, grouped by agency + topic keywords.
Regulatory activity = government is paying attention = legitimizing or constraining a market.
Fires if topic appears in 3+ proposed rules.
signal_category: builder (regulatory change = opportunity to build compliant solutions)
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

FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/documents.json"

# Document types that signal regulatory intent
DOCUMENT_TYPES = [
    "PRORULE",   # Proposed Rule
    "RULE",      # Final Rule
    "NOTICE",    # Notice
    "PRESDOCU",  # Presidential Document
]

# Agency abbreviations to watch for tech/innovation impact
PRIORITY_AGENCIES = {
    "FTC": "Federal Trade Commission",
    "SEC": "Securities and Exchange Commission",
    "FDA": "Food and Drug Administration",
    "FCC": "Federal Communications Commission",
    "CFPB": "Consumer Financial Protection Bureau",
    "DOE": "Department of Energy",
    "EPA": "Environmental Protection Agency",
    "USPTO": "Patent and Trademark Office",
    "NIST": "National Institute of Standards and Technology",
    "OSTP": "Office of Science and Technology Policy",
    "NTIA": "National Telecommunications and Information Administration",
    "CISA": "Cybersecurity and Infrastructure Security Agency",
    "NSF": "National Science Foundation",
    "NIH": "National Institutes of Health",
    "DARPA": "Defense Advanced Research Projects Agency",
    "DOD": "Department of Defense",
    "DOT": "Department of Transportation",
    "HHS": "Department of Health and Human Services",
    "CMS": "Centers for Medicare and Medicaid Services",
    "FinCEN": "Financial Crimes Enforcement Network",
}

# Technology keyword groups for document classification
TECH_KEYWORD_GROUPS = {
    "artificial intelligence": [
        "artificial intelligence", "machine learning", "algorithmic",
        "automated decision", "AI system", "large language model",
        "generative AI", "foundation model", "facial recognition",
        "predictive analytics",
    ],
    "cryptocurrency & blockchain": [
        "cryptocurrency", "digital asset", "blockchain", "stablecoin",
        "DeFi", "NFT", "virtual currency", "crypto",
        "distributed ledger", "tokenization",
    ],
    "privacy & data": [
        "data privacy", "personal information", "data protection",
        "surveillance", "biometric", "facial recognition",
        "location data", "consumer data",
    ],
    "cybersecurity": [
        "cybersecurity", "cyber incident", "zero trust", "software security",
        "vulnerability disclosure", "ransomware", "critical infrastructure",
        "open source software security",
    ],
    "clean energy": [
        "clean energy", "renewable energy", "electric vehicle", "EV",
        "battery storage", "hydrogen", "carbon capture", "solar",
        "offshore wind", "grid modernization",
    ],
    "biotechnology": [
        "biotechnology", "gene editing", "CRISPR", "synthetic biology",
        "genomic", "cell therapy", "mRNA", "biosecurity",
        "biodefense", "pathogen",
    ],
    "autonomous vehicles": [
        "autonomous vehicle", "self-driving", "unmanned aircraft",
        "drone", "ADAS", "vehicle automation", "connected vehicle",
    ],
    "space technology": [
        "commercial space", "satellite", "orbital", "space launch",
        "spectrum allocation", "GPS", "low earth orbit",
    ],
    "fintech & payments": [
        "fintech", "open banking", "real-time payment", "BNPL",
        "digital payment", "payment processing", "interchange",
    ],
    "telecom & connectivity": [
        "5G", "broadband", "spectrum", "wireless", "fiber",
        "internet access", "net neutrality", "rural broadband",
    ],
    "healthcare technology": [
        "telehealth", "digital health", "health technology",
        "medical device", "clinical decision support", "wearable",
        "remote patient monitoring", "electronic health record",
    ],
    "quantum technology": [
        "quantum computing", "quantum sensing", "quantum communication",
        "post-quantum cryptography", "quantum information",
    ],
}

MIN_FIRE_COUNT = 3  # Minimum documents for a topic to fire


@retry_with_backoff(max_retries=3)
def _fetch_documents(
    document_types: list[str],
    days: int = 14,
    page: int = 1,
    per_page: int = 100,
) -> dict:
    """
    Fetch documents from Federal Register API.
    Returns raw API response.
    """
    start_date = (date.today() - timedelta(days=days)).strftime("%m/%d/%Y")

    params = {
        "conditions[type][]": document_types,
        "conditions[publication_date][gte]": start_date,
        "fields[]": [
            "document_number",
            "title",
            "abstract",
            "type",
            "publication_date",
            "agencies",
            "action",
            "html_url",
            "effective_on",
        ],
        "per_page": per_page,
        "page": page,
        "order": "newest",
    }

    response = httpx.get(
        FEDERAL_REGISTER_API,
        params=params,
        timeout=30,
        headers={"User-Agent": "zeitgeist/1.0"},
    )
    response.raise_for_status()
    return response.json()


def _classify_document(title: str, abstract: str) -> list[str]:
    """
    Match document text against TECH_KEYWORD_GROUPS.
    Returns list of matching category names.
    """
    text = f"{title} {abstract}".lower()
    matched = []
    for category, keywords in TECH_KEYWORD_GROUPS.items():
        for kw in keywords:
            if kw.lower() in text:
                matched.append(category)
                break
    return matched


def _extract_keywords(title: str, abstract: str, top_n: int = 8) -> list[str]:
    """Extract most frequent meaningful words from document text."""
    STOPWORDS = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "for", "of", "and", "or", "but", "not", "with", "this",
        "that", "it", "in", "on", "at", "to", "by", "from", "as",
        "proposed", "rule", "notice", "agency", "final", "document",
        "federal", "register", "comment", "period", "action",
        "pursuant", "section", "under", "part", "title", "act",
        "united", "states", "government", "public", "new", "order",
    }
    text = f"{title} {abstract}"
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{3,}\b", text.lower())
    counts = Counter(w for w in words if w not in STOPWORDS)
    return [w for w, _ in counts.most_common(top_n)]


def collect() -> list[dict]:
    """
    Fetches Federal Register proposed rules and notices from last 14 days.
    Groups by agency + topic keywords to find regulatory clusters.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, document_count,
                     agencies, sample_titles, document_type}.
    Fires if topic appears in 3+ proposed rules.
    signal_category: builder
    """
    logger.info("Collecting Federal Register regulatory signals...")
    results = []

    all_documents = []

    # Fetch proposed rules and notices
    for doc_types_batch in [["PRORULE", "RULE"], ["NOTICE"]]:
        page = 1
        while page <= 5:  # Cap at 500 documents
            try:
                data = _fetch_documents(
                    document_types=doc_types_batch,
                    days=14,
                    page=page,
                    per_page=100,
                )

                docs = data.get("results", [])
                if not docs:
                    break

                all_documents.extend(docs)
                count_on_page = data.get("count", 0)

                logger.debug(
                    f"Federal Register: page {page}, "
                    f"{len(docs)} docs fetched (total available: {count_on_page})"
                )

                # Check if there are more pages
                total_pages = data.get("total_pages", 1)
                if page >= total_pages:
                    break

                page += 1
                time.sleep(1)

            except Exception as e:
                logger.warning(f"Federal Register: failed to fetch page {page}: {e}")
                break

    if not all_documents:
        logger.warning("Federal Register: no documents fetched")
        return results

    logger.debug(f"Federal Register: {len(all_documents)} total documents")

    # Classify each document and aggregate
    topic_docs: dict[str, list[dict]] = defaultdict(list)
    topic_agencies: dict[str, set] = defaultdict(set)

    for doc in all_documents:
        title = doc.get("title", "") or ""
        abstract = doc.get("abstract", "") or ""
        doc_type = doc.get("type", "")
        pub_date = doc.get("publication_date", "")
        doc_url = doc.get("html_url", "")

        # Agency extraction
        agencies_raw = doc.get("agencies", []) or []
        agency_names = []
        for agency in agencies_raw:
            if isinstance(agency, dict):
                name = agency.get("name", "") or agency.get("raw_name", "")
                if name:
                    agency_names.append(name)
            elif isinstance(agency, str):
                agency_names.append(agency)

        categories = _classify_document(title, abstract)

        for category in categories:
            topic_docs[category].append({
                "title": title[:120],
                "type": doc_type,
                "date": pub_date,
                "url": doc_url,
                "agencies": agency_names,
            })
            for agency in agency_names:
                topic_agencies[category].add(agency)

    if not topic_docs:
        logger.warning("Federal Register: no documents matched any tech keyword group")
        # Fallback: return top agencies as general signals
        agency_counts: dict[str, int] = defaultdict(int)
        for doc in all_documents:
            for agency in (doc.get("agencies", []) or []):
                if isinstance(agency, dict):
                    name = agency.get("name", "")
                    if name:
                        agency_counts[name] += 1

        for agency, count in sorted(agency_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            results.append({
                "topic": f"agency:{agency}",
                "raw_value": count,
                "baseline_value": None,
                "spike_score": round(count / max(agency_counts.values(), default=1), 4),
                "signal_source": "federal_register",
                "signal_category": "builder",
                "fired": count >= MIN_FIRE_COUNT,
                "document_count": count,
                "agencies": [agency],
                "sample_titles": [],
            })
        return results

    max_count = max(len(v) for v in topic_docs.values())

    for topic, docs in sorted(
        topic_docs.items(), key=lambda x: len(x[1]), reverse=True
    ):
        count = len(docs)
        agencies = list(topic_agencies.get(topic, set()))[:5]
        sample_titles = [d["title"] for d in docs[:3]]

        # Count by document type
        type_counts = Counter(d["type"] for d in docs)

        spike_score = count / max_count if max_count > 0 else 0.0

        results.append({
            "topic": topic,
            "raw_value": count,
            "baseline_value": None,  # No historical baseline without DB
            "spike_score": round(spike_score, 4),
            "signal_source": "federal_register",
            "signal_category": "builder",
            "fired": count >= MIN_FIRE_COUNT,
            "document_count": count,
            "proposed_rules": type_counts.get("PRORULE", 0),
            "final_rules": type_counts.get("RULE", 0),
            "notices": type_counts.get("NOTICE", 0),
            "agencies": agencies,
            "sample_titles": sample_titles,
        })

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(
        f"Federal Register: {len(all_documents)} documents, "
        f"{len(results)} topic signals, {fired_count} fired (3+ documents)"
    )
    return results
