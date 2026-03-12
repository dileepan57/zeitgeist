"""
USPTO Patent + Trademark signal collector.
Uses PatentsView API (https://search.patentsview.org/api/v1/patent/) to
fetch patents filed in last 30 days grouped by CPC technology class.
Also attempts to identify trademark filing surges via USPTO TESS.
Patent filing spikes = builders are protecting IP in a new area = strong builder signal.
signal_category: builder
"""
import re
import time
from collections import defaultdict
from datetime import date, timedelta
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

PATENTSVIEW_API = "https://search.patentsview.org/api/v1/patent/"
USPTO_TRADEMARK_SEARCH = "https://efts.uspto.gov/LATEST/search-efts/hits"

# CPC (Cooperative Patent Classification) technology sections to monitor
# These map to major technology domains
CPC_SECTIONS = {
    "G06N": "AI & Machine Learning",
    "G06F": "Computing Hardware & Software",
    "G06T": "Image Processing & Vision",
    "G06V": "Image/Video Recognition",
    "G16H": "Healthcare Informatics",
    "G16B": "Bioinformatics",
    "H04L": "Data Communications",
    "H04W": "Wireless Communications",
    "B60W": "Autonomous Vehicles",
    "A61B": "Medical Diagnosis",
    "A61K": "Pharmaceuticals",
    "C12N": "Microbiology & Biotech",
    "C12Q": "Measuring Biological Processes",
    "H01L": "Semiconductors",
    "H02J": "Energy Storage & Grid",
    "F03D": "Wind Energy",
    "H01M": "Electrochemical Processes (Batteries)",
    "B82": "Nanotechnology",
    "G01S": "Radar/Lidar/Sonar",
    "G08G": "Traffic Control Systems",
}

# Keyword categories for trademark trend detection
TRADEMARK_KEYWORDS = [
    "AI", "artificial intelligence", "generative", "neural",
    "autonomous", "robot", "quantum", "biotech", "gene",
    "crypto", "blockchain", "metaverse", "spatial", "holographic",
    "climate", "carbon", "renewable", "fusion", "battery",
]


@retry_with_backoff(max_retries=3)
def _fetch_patents_by_cpc(cpc_code: str, days: int = 30) -> dict:
    """
    Fetch patent applications filed in the last N days for a CPC code section.
    Returns total count and sample patent titles.
    """
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    # PatentsView API uses POST with JSON body
    payload = {
        "q": {
            "_and": [
                {"_gte": {"patent_date": start_date}},
                {"_begins": {"cpc_section_id": cpc_code[0]}},  # Use section letter
            ]
        },
        "f": ["patent_id", "patent_title", "patent_date", "cpc_section_id", "cpc_subgroup_id"],
        "o": {"per_page": 100, "page": 1, "sort": [{"patent_date": "desc"}]},
    }

    # PatentsView has different query structure — use simpler approach
    params = {
        "q": f'{{"_and":[{{"_gte":{{"patent_date":"{start_date}"}}}},{{"_begins":{{"cpc_section_id":"{cpc_code[0]}"}}}}]}}',
        "f": '["patent_id","patent_title","patent_date","cpc_section_id"]',
        "o": '{"per_page":50,"page":1}',
    }

    response = httpx.get(PATENTSVIEW_API, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()

    total = data.get("total_patent_count", 0)
    patents = data.get("patents", [])

    return {
        "total": total,
        "sample_titles": [p.get("patent_title", "") for p in patents[:5] if p.get("patent_title")],
    }


@retry_with_backoff(max_retries=3)
def _fetch_patents_cpc_full(cpc_prefix: str, days: int = 30) -> dict:
    """
    Fetch patents using CPC subsection prefix via PatentsView REST API.
    Uses the newer v1 endpoint format.
    """
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Build query for PatentsView v1 API
    query = {
        "_and": [
            {"_gte": {"patent_date": start_date}},
        ]
    }

    import json
    params = {
        "q": json.dumps(query),
        "f": json.dumps(["patent_id", "patent_title", "patent_date",
                          "cpc_category", "cpc_subgroup_id"]),
        "o": json.dumps({"per_page": 100, "page": 1, "sort": [{"patent_date": "desc"}]}),
    }

    response = httpx.get(PATENTSVIEW_API, params=params, timeout=45)
    response.raise_for_status()
    data = response.json()
    return data


@retry_with_backoff(max_retries=3)
def _search_trademark_filings(keyword: str, days: int = 30) -> int:
    """
    Search USPTO TESS (Trademark Electronic Search System) for new filings
    containing a keyword. Uses the EFTS (ElasticSearch) endpoint.
    """
    start_date = (date.today() - timedelta(days=days)).strftime("%Y-%m-%d")

    params = {
        "q": keyword,
        "dateRangeField": "serialDate",
        "dateRange": "custom",
        "startDate": start_date,
        "endDate": date.today().strftime("%Y-%m-%d"),
    }

    headers = {
        "User-Agent": "zeitgeist/1.0",
        "Accept": "application/json",
    }

    response = httpx.get(USPTO_TRADEMARK_SEARCH, params=params, headers=headers, timeout=30)
    if response.status_code == 404:
        return 0
    response.raise_for_status()

    data = response.json()
    hits = data.get("hits", {})
    total = hits.get("total", {})
    if isinstance(total, dict):
        return total.get("value", 0)
    return int(total) if total else 0


def _extract_keywords_from_titles(titles: list[str]) -> dict[str, int]:
    """Extract technology keyword frequencies from patent titles."""
    STOPWORDS = {
        "method", "system", "apparatus", "device", "process", "using",
        "based", "and", "for", "the", "with", "via", "improved", "novel",
        "new", "approach", "technique", "a", "an", "of", "in", "on", "to",
    }
    keyword_counts: dict[str, int] = defaultdict(int)

    for title in titles:
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", title.lower())
        filtered = [w for w in words if w not in STOPWORDS]

        for word in filtered:
            keyword_counts[word] += 1

        # Bigrams
        for i in range(len(filtered) - 1):
            bigram = f"{filtered[i]} {filtered[i+1]}"
            keyword_counts[bigram] += 1

    return dict(keyword_counts)


def collect() -> list[dict]:
    """
    Collects patent filing signals from USPTO PatentsView API,
    grouped by CPC technology class.
    Also collects trademark filing trend signals.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, patent_count,
                     cpc_code, top_keywords}.
    signal_category: builder
    """
    logger.info("Collecting USPTO patent/trademark signals...")
    results = []

    # --- PatentsView CPC-based patent signals ---
    try:
        # Fetch a broad sample of recent patents
        patent_data = _fetch_patents_cpc_full("", days=30)
        all_patents = patent_data.get("patents", [])
        total_recent = patent_data.get("total_patent_count", 0)

        if all_patents:
            # Group patents by CPC section
            cpc_groups: dict[str, list[str]] = defaultdict(list)
            for patent in all_patents:
                title = patent.get("patent_title", "")
                cpc_id = patent.get("cpc_subgroup_id", "") or patent.get("cpc_category", "")

                if cpc_id:
                    # Extract prefix (first 4 chars like "G06N")
                    prefix = cpc_id[:4].upper()
                    if prefix in CPC_SECTIONS:
                        cpc_groups[prefix].append(title)

            if cpc_groups:
                max_group_count = max(len(v) for v in cpc_groups.values())

                for cpc_code, titles in cpc_groups.items():
                    count = len(titles)
                    theme = CPC_SECTIONS.get(cpc_code, cpc_code)
                    keywords = _extract_keywords_from_titles(titles)
                    top_kw = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:5]

                    spike_score = count / max_group_count if max_group_count > 0 else 0.0

                    results.append({
                        "topic": f"patent:{theme}",
                        "raw_value": count,
                        "baseline_value": None,
                        "spike_score": round(spike_score, 4),
                        "signal_source": "patentsview",
                        "signal_category": "builder",
                        "fired": count >= 5 and spike_score >= 0.2,
                        "patent_count": count,
                        "cpc_code": cpc_code,
                        "cpc_theme": theme,
                        "top_keywords": [kw for kw, _ in top_kw],
                    })

        logger.debug(f"PatentsView: {len(results)} CPC groups processed")

    except Exception as e:
        logger.warning(f"PatentsView: API fetch failed: {e}")

        # Fallback: Try individual CPC section queries
        for cpc_code, theme in list(CPC_SECTIONS.items())[:10]:  # Limit to avoid hammering
            try:
                data = _fetch_patents_by_cpc(cpc_code, days=30)
                count = data["total"]
                sample_titles = data["sample_titles"]

                if count == 0:
                    continue

                keywords = _extract_keywords_from_titles(sample_titles)
                top_kw = sorted(keywords.items(), key=lambda x: x[1], reverse=True)[:5]

                results.append({
                    "topic": f"patent:{theme}",
                    "raw_value": count,
                    "baseline_value": None,
                    "spike_score": 0.5,  # Can't normalize without full dataset
                    "signal_source": "patentsview",
                    "signal_category": "builder",
                    "fired": count >= 50,
                    "patent_count": count,
                    "cpc_code": cpc_code,
                    "cpc_theme": theme,
                    "top_keywords": [kw for kw, _ in top_kw],
                })

                time.sleep(2)

            except Exception as e2:
                logger.debug(f"PatentsView fallback failed for {cpc_code}: {e2}")

    time.sleep(2)

    # --- USPTO Trademark Signals ---
    trademark_counts: dict[str, int] = {}

    for keyword in TRADEMARK_KEYWORDS:
        try:
            count = _search_trademark_filings(keyword, days=30)
            trademark_counts[keyword] = count
            logger.debug(f"USPTO Trademark '{keyword}': {count} filings (30d)")
            time.sleep(2)
        except Exception as e:
            logger.debug(f"USPTO Trademark search failed for '{keyword}': {e}")

    if trademark_counts:
        max_tm_count = max(trademark_counts.values()) if trademark_counts.values() else 1
        for keyword, count in trademark_counts.items():
            if count == 0:
                continue
            spike_score = count / max_tm_count if max_tm_count > 0 else 0.0
            results.append({
                "topic": f"trademark:{keyword}",
                "raw_value": count,
                "baseline_value": None,
                "spike_score": round(spike_score, 4),
                "signal_source": "uspto_trademark",
                "signal_category": "builder",
                "fired": count >= 10 and spike_score >= 0.1,
                "trademark_filings_30d": count,
                "keyword": keyword,
            })

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(f"USPTO: {len(results)} signals, {fired_count} fired")
    return results
